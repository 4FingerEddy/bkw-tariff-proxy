from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .normalizer import TariffNormalizationError, TariffPayloadError, normalize_bkw_payload


STATUS_CODES = {
    "ok": 0,
    "no_data": 1,
    "stale": 2,
    "api_error": 3,
    "partial_horizon": 4,
    "unit_unknown": 5,
}

logger = logging.getLogger(__name__)
EXPECTED_LIVE_INTERVALS_PER_HOUR = 4


@dataclass
class TariffState:
    status: str = "no_data"
    normalized: dict[str, Any] = field(default_factory=lambda: {"status": "no_data", "relative": []})
    updated_at: str | None = None
    last_error: str | None = None
    last_http_status: int | None = None


def build_synthetic_bkw_payload(now: datetime, *, horizon_hours: int = 24) -> dict[str, Any]:
    """Build deterministic rolling test data that looks like BKW TariffDto.

    This is for Loxone integration tests while the public BKW endpoint returns
    404. Values are plausible, but explicitly fake.
    """

    base = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    prices: list[dict[str, Any]] = []
    for offset in range(horizon_hours):
        start = base + timedelta(hours=offset)
        end = start + timedelta(hours=1)
        value = round(0.045 + ((offset * 7) % 17) / 1000, 6)
        prices.append(
            {
                "start_timestamp": start.isoformat(),
                "end_timestamp": end.isoformat(),
                "feed_in": [{"unit": "CHF/kWh", "value": value}],
            }
        )
    return {
        "publication_timestamp": now.astimezone(timezone.utc).isoformat(),
        "prices": prices,
    }


class TariffService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache_path = Path(settings.data_dir) / "cache.json"
        self.state = self._load_cache()

    def _load_cache(self) -> TariffState:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return TariffState(**data)
        except FileNotFoundError:
            return TariffState()
        except Exception as exc:
            return TariffState(status="no_data", last_error=f"cache_load_failed: {exc}")

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.state.__dict__, indent=2, sort_keys=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".cache.", suffix=".json", dir=self.cache_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(payload)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_name, self.cache_path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass

    def _derive_status(self, normalized: dict[str, Any], *, live_quarter_hour_data: bool) -> str:
        status = normalized["status"]
        if status == "ok" and self.settings.require_full_horizon:
            if normalized.get("horizon_hours", 0) < 24:
                return "partial_horizon"
            if live_quarter_hour_data and normalized.get("min_interval_count", 0) < EXPECTED_LIVE_INTERVALS_PER_HOUR:
                return "partial_horizon"
        return status

    def _set_status(self, status: str, *, reason: str | None = None) -> None:
        previous = self.state.status
        self.state.status = status
        if status != previous or status != "ok":
            logger.warning("BKW tariff status=%s previous=%s reason=%s", status, previous, reason)

    async def refresh_once(self) -> TariffState:
        try:
            if self.settings.test_data_mode == "synthetic":
                now = datetime.now(timezone.utc)
                normalized = normalize_bkw_payload(build_synthetic_bkw_payload(now), now=now)
                status = self._derive_status(normalized, live_quarter_hour_data=False)
                self.state = TariffState(
                    status=status,
                    normalized=normalized,
                    updated_at=now.isoformat(),
                    last_error=None,
                    last_http_status=None,
                )
                self._save_cache()
                return self.state

            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(self.settings.bkw_endpoint)
            self.state.last_http_status = response.status_code
            if response.status_code == 404:
                self._set_status("no_data", reason="BKW endpoint returned 404/no_data")
                self.state.last_error = "BKW endpoint returned 404/no_data"
                self._save_cache()
                return self.state
            response.raise_for_status()
            normalized = normalize_bkw_payload(response.json(), now=datetime.now(timezone.utc))
            status = self._derive_status(normalized, live_quarter_hour_data=True)
            self.state = TariffState(
                status=status,
                normalized=normalized,
                updated_at=datetime.now(timezone.utc).isoformat(),
                last_error=None,
                last_http_status=response.status_code,
            )
            self._save_cache()
            return self.state
        except TariffPayloadError as exc:
            self._set_status("api_error", reason=str(exc))
            self.state.last_error = str(exc)
            self._save_cache()
            return self.state
        except TariffNormalizationError as exc:
            self._set_status("unit_unknown", reason=str(exc))
            self.state.last_error = str(exc)
            self._save_cache()
            return self.state
        except Exception as exc:
            self._set_status("api_error", reason=str(exc))
            self.state.last_error = str(exc)
            self._save_cache()
            return self.state

    def effective_status(self) -> str:
        if self.state.status == "ok" and self.state.updated_at:
            try:
                updated_at = datetime.fromisoformat(self.state.updated_at.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)
                if age.total_seconds() > self.settings.cache_max_age_seconds:
                    return "stale"
            except ValueError:
                return "stale"
        return self.state.status

    def status_code(self) -> int:
        return STATUS_CODES.get(self.effective_status(), 99)

    def relative_value(self, offset: int) -> float | None:
        for slot in self.state.normalized.get("relative", []):
            if slot.get("offset") == offset:
                return slot.get("value")
        return None

    def safe_relative_value(self, offset: int) -> float | None:
        if self.effective_status() != "ok":
            return None
        return self.relative_value(offset)

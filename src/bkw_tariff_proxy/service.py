from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .normalizer import TariffNormalizationError, normalize_bkw_payload


STATUS_CODES = {
    "ok": 0,
    "no_data": 1,
    "stale": 2,
    "api_error": 3,
    "partial_horizon": 4,
    "unit_unknown": 5,
}


@dataclass
class TariffState:
    status: str = "no_data"
    normalized: dict[str, Any] = field(default_factory=lambda: {"status": "no_data", "relative": []})
    updated_at: str | None = None
    last_error: str | None = None
    last_http_status: int | None = None


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
        self.cache_path.write_text(
            json.dumps(self.state.__dict__, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    async def refresh_once(self) -> TariffState:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(self.settings.bkw_endpoint)
            self.state.last_http_status = response.status_code
            if response.status_code == 404:
                self.state.status = "no_data"
                self.state.last_error = "BKW endpoint returned 404/no_data"
                self._save_cache()
                return self.state
            response.raise_for_status()
            normalized = normalize_bkw_payload(response.json(), now=datetime.now(timezone.utc))
            status = normalized["status"]
            if status == "ok" and self.settings.require_full_horizon and normalized.get("horizon_hours", 0) < 24:
                status = "partial_horizon"
            self.state = TariffState(
                status=status,
                normalized=normalized,
                updated_at=datetime.now(timezone.utc).isoformat(),
                last_error=None,
                last_http_status=response.status_code,
            )
            self._save_cache()
            return self.state
        except TariffNormalizationError as exc:
            self.state.status = "unit_unknown"
            self.state.last_error = str(exc)
            self._save_cache()
            return self.state
        except Exception as exc:
            self.state.status = "api_error"
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

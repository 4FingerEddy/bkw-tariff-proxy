from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .normalizer import (
    TariffNormalizationError,
    TariffPayloadError,
    build_relative_from_days,
    normalize_bkw_payload,
)


STATUS_CODES = {
    "ok": 0,
    "no_data": 1,
    "stale": 2,
    "api_error": 3,
    "partial_horizon": 4,
    "unit_unknown": 5,
}

logger = logging.getLogger(__name__)


@dataclass
class TariffState:
    status: str = "no_data"
    normalized: dict[str, Any] = field(default_factory=lambda: {"status": "no_data", "days": {}, "relative": []})
    updated_at: str | None = None
    upstream_last_success_at: str | None = None
    last_error: str | None = None
    last_http_status: int | None = None


def build_synthetic_bkw_payload(now: datetime, *, timezone_name: str = "Europe/Zurich") -> dict[str, Any]:
    """Build deterministic full-day test data that looks like BKW TariffDto."""

    tz = ZoneInfo(timezone_name)
    local_start = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    prices: list[dict[str, Any]] = []
    for index in range(96):
        start_local = local_start + timedelta(minutes=15 * index)
        end_local = start_local + timedelta(minutes=15)
        hour = start_local.hour
        value = round(0.045 + ((hour * 7) % 17) / 1000, 6)
        prices.append(
            {
                "start_timestamp": start_local.astimezone(timezone.utc).isoformat(),
                "end_timestamp": end_local.astimezone(timezone.utc).isoformat(),
                "feed_in": [{"unit": "CHF/kWh", "value": value}],
            }
        )
    return {
        "publication_timestamp": now.astimezone(timezone.utc).isoformat(),
        "prices": prices,
    }


class TariffService:
    def __init__(self, settings: Settings, *, now_provider: Callable[[], datetime] | None = None):
        self.settings = settings
        self.cache_path = Path(settings.data_dir) / "cache.json"
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.state = self._load_cache()
        self._refresh_derived_views()

    def now(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

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

    def _local_today(self) -> str:
        return self.now().astimezone(ZoneInfo(self.settings.timezone)).date().isoformat()

    def _local_tomorrow(self) -> str:
        today = self.now().astimezone(ZoneInfo(self.settings.timezone)).date()
        return (today + timedelta(days=1)).isoformat()

    def _day_complete(self, day: dict[str, Any] | None) -> bool:
        if not day:
            return False
        if day.get("received_intervals") != day.get("expected_intervals"):
            return False
        for hour in day.get("hours", []):
            if hour.get("dst_placeholder"):
                continue
            if hour.get("value_chf_kwh") is None:
                return False
            expected = 8 if day.get("expected_intervals") == 100 and hour.get("hour") == 2 else 4
            if hour.get("interval_count") != expected:
                return False
        return len(day.get("hours", [])) == 24

    def _merge_day(self, day: dict[str, Any]) -> None:
        days = dict(self.state.normalized.get("days") or {})
        tariff_date = day["tariff_date"]
        old = days.get(tariff_date)
        if old and old.get("content_hash") != day.get("content_hash"):
            logger.warning("BKW intraday tariff value change detected for %s", tariff_date)
        days[tariff_date] = day

        today = self._local_today()
        tomorrow = self._local_tomorrow()
        self.state.normalized["days"] = {key: value for key, value in days.items() if key in {today, tomorrow}}

    def _refresh_derived_views(self) -> None:
        days = self.state.normalized.get("days") or {}
        today = self._local_today()
        tomorrow = self._local_tomorrow()
        today_day = days.get(today)
        tomorrow_day = days.get(tomorrow)
        relative = build_relative_from_days(
            days,
            now=self.now(),
            timezone_name=self.settings.timezone,
            horizon_hours=24,
        )
        self.state.normalized.update(
            {
                "unit": "CHF/kWh",
                "today_date": today_day.get("tariff_date") if today_day else None,
                "tomorrow_date": tomorrow_day.get("tariff_date") if tomorrow_day else None,
                "day_today_status": self._day_status(today_day, expected_date=today),
                "day_tomorrow_status": self._day_status(tomorrow_day, expected_date=tomorrow, missing_status="pending"),
                "horizon_hours": len(relative),
                "relative": [slot.as_dict() for slot in relative],
            }
        )

    def _day_status(self, day: dict[str, Any] | None, *, expected_date: str, missing_status: str = "no_data") -> str:
        if not day:
            return missing_status
        if day.get("tariff_date") != expected_date:
            return "stale"
        return "ok" if self._day_complete(day) else "partial_horizon"

    def _derive_status(self, *, fetch_status: str | None = None) -> str:
        days = self.state.normalized.get("days") or {}
        today = self._local_today()
        today_day = days.get(today)
        today_status = self._day_status(today_day, expected_date=today)
        if today_status == "ok":
            return "ok"
        if today_status == "partial_horizon":
            return "partial_horizon"
        if fetch_status in {"unit_unknown", "api_error"}:
            return fetch_status
        return "no_data"

    def _set_status(self, status: str, *, reason: str | None = None) -> None:
        previous = self.state.status
        self.state.status = status
        self.state.normalized["status"] = status
        if status != previous or status != "ok":
            logger.warning("BKW tariff status=%s previous=%s reason=%s", status, previous, reason)

    async def refresh_once(self) -> TariffState:
        now = self.now()
        try:
            if self.settings.test_data_mode == "synthetic":
                normalized = normalize_bkw_payload(
                    build_synthetic_bkw_payload(now, timezone_name=self.settings.timezone),
                    now=now,
                    timezone_name=self.settings.timezone,
                )
                day = normalized.get("day")
                if day:
                    self._merge_day(day)
                self.state.updated_at = now.isoformat()
                self.state.upstream_last_success_at = now.isoformat()
                self.state.last_error = None
                self.state.last_http_status = None
                self._refresh_derived_views()
                self._set_status(self._derive_status(fetch_status=normalized["status"]))
                self._save_cache()
                return self.state

            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(self.settings.bkw_endpoint)
            self.state.last_http_status = response.status_code
            if response.status_code == 404:
                self.state.updated_at = now.isoformat()
                self.state.last_error = "BKW endpoint returned 404/no_data"
                self._refresh_derived_views()
                self._set_status(self._derive_status(fetch_status="no_data"), reason="BKW endpoint returned 404/no_data")
                self._save_cache()
                return self.state
            response.raise_for_status()
            normalized = normalize_bkw_payload(response.json(), now=now, timezone_name=self.settings.timezone)
            day = normalized.get("day")
            if day:
                self._merge_day(day)
            self.state.updated_at = now.isoformat()
            self.state.upstream_last_success_at = now.isoformat()
            self.state.last_error = None
            self.state.last_http_status = response.status_code
            self.state.normalized["publication_timestamp"] = normalized.get("publication_timestamp")
            self._refresh_derived_views()
            self._set_status(self._derive_status(fetch_status=normalized["status"]))
            self._save_cache()
            return self.state
        except TariffPayloadError as exc:
            self.state.updated_at = now.isoformat()
            self.state.last_error = str(exc)
            self._refresh_derived_views()
            self._set_status(self._derive_status(fetch_status="api_error"), reason=str(exc))
            self._save_cache()
            return self.state
        except TariffNormalizationError as exc:
            self.state.updated_at = now.isoformat()
            self.state.last_error = str(exc)
            self._refresh_derived_views()
            self._set_status("unit_unknown", reason=str(exc))
            self._save_cache()
            return self.state
        except Exception as exc:
            self.state.updated_at = now.isoformat()
            self.state.last_error = str(exc)
            self._refresh_derived_views()
            self._set_status(self._derive_status(fetch_status="api_error"), reason=str(exc))
            self._save_cache()
            return self.state

    def effective_status(self) -> str:
        self._refresh_derived_views()
        status = self._derive_status(fetch_status=self.state.status)
        self.state.status = status
        self.state.normalized["status"] = status
        return status

    def status_code(self) -> int:
        return STATUS_CODES.get(self.effective_status(), 99)

    def upstream_age_seconds(self) -> int | None:
        if not self.state.upstream_last_success_at:
            return None
        try:
            updated_at = datetime.fromisoformat(self.state.upstream_last_success_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(0, int((self.now().astimezone(timezone.utc) - updated_at.astimezone(timezone.utc)).total_seconds()))

    def current_day(self) -> dict[str, Any] | None:
        self._refresh_derived_views()
        return (self.state.normalized.get("days") or {}).get(self._local_today())

    def tomorrow_day(self) -> dict[str, Any] | None:
        self._refresh_derived_views()
        return (self.state.normalized.get("days") or {}).get(self._local_tomorrow())

    def day_hour_value(self, hour: int) -> float | None:
        if hour < 0 or hour > 23:
            raise ValueError("hour must be 0..23")
        day = self.current_day()
        if not day:
            return None
        return day["hours"][hour].get("value_chf_kwh")

    def safe_day_hour_value(self, hour: int) -> float | None:
        if self.effective_status() != "ok":
            return None
        return self.day_hour_value(hour)

    def current_value(self) -> float | None:
        current_hour = self.now().astimezone(ZoneInfo(self.settings.timezone)).hour
        return self.day_hour_value(current_hour)

    def safe_current_value(self) -> float | None:
        if self.effective_status() != "ok":
            return None
        return self.current_value()

    def relative_value(self, offset: int) -> float | None:
        self._refresh_derived_views()
        for slot in self.state.normalized.get("relative", []):
            if slot.get("offset") == offset:
                return slot.get("value")
        return None

    def safe_relative_value(self, offset: int) -> float | None:
        if self.effective_status() != "ok":
            return None
        return self.relative_value(offset)

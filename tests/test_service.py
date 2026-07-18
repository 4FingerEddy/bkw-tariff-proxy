import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from bkw_tariff_proxy.config import Settings
from bkw_tariff_proxy.normalizer import normalize_bkw_payload
from bkw_tariff_proxy.service import TariffService

TZ = ZoneInfo("Europe/Zurich")


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):
        return self.response


class RaisingAsyncClient:
    def __init__(self, exc):
        self.exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):
        raise self.exc


def make_settings(tmp_path, **overrides):
    defaults = {
        "bkw_endpoint": "https://example.invalid/tariffs",
        "poll_interval_seconds": 900,
        "cache_max_age_seconds": 60,
        "upstream_warn_age_seconds": 7200,
        "data_dir": str(tmp_path),
        "timezone": "Europe/Zurich",
        "require_complete_day": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_service(tmp_path, now: datetime, **settings_overrides):
    return TariffService(make_settings(tmp_path, **settings_overrides), now_provider=lambda: now)


def make_day_payload(day: str, *, missing: int = 0, value_base: float = 0.04, unit: str = "CHF_kWh"):
    start = datetime.fromisoformat(day).replace(tzinfo=TZ)
    prices = []
    for index in range(96 - missing):
        interval_start = start + timedelta(minutes=15 * index)
        hour = interval_start.hour
        value = round(value_base + hour / 1000, 6)
        prices.append(
            {
                "start_timestamp": interval_start.astimezone(ZoneInfo("UTC")).isoformat(),
                "end_timestamp": (interval_start + timedelta(minutes=15)).astimezone(ZoneInfo("UTC")).isoformat(),
                "feed_in": [{"unit": unit, "value": value}],
            }
        )
    return {"publication_timestamp": f"{day}T12:00:00Z", "prices": prices}


def patch_response(monkeypatch, payload, status_code=200):
    response = httpx.Response(status_code, json=payload, request=httpx.Request("GET", "https://example.invalid/tariffs"))
    monkeypatch.setattr("bkw_tariff_proxy.service.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient(response))


def test_bkw_404_is_no_data_and_persisted(tmp_path, monkeypatch):
    response = httpx.Response(404, request=httpx.Request("GET", "https://example.invalid/tariffs"))
    monkeypatch.setattr("bkw_tariff_proxy.service.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient(response))
    service = make_service(tmp_path, datetime.fromisoformat("2026-07-04T08:00:00+02:00"))

    state = asyncio.run(service.refresh_once())

    assert state.status == "no_data"
    assert state.last_http_status == 404
    assert "404" in state.last_error
    cache = json.loads(Path(tmp_path, "cache.json").read_text())
    assert cache["status"] == "no_data"


def test_complete_today_dataset_is_ok_all_day(tmp_path, monkeypatch):
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    patch_response(monkeypatch, make_day_payload("2026-07-04"))
    service = make_service(tmp_path, now)

    state = asyncio.run(service.refresh_once())

    assert state.status == "ok"
    assert service.status_code() == 0
    assert service.safe_day_hour_value(0) == 0.04
    assert service.safe_day_hour_value(23) == 0.063
    assert service.safe_current_value() == 0.048
    assert state.normalized["day_today_status"] == "ok"
    assert state.normalized["horizon_hours"] == 16


def test_cache_age_does_not_make_valid_today_stale(tmp_path, monkeypatch):
    morning = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    patch_response(monkeypatch, make_day_payload("2026-07-04"))
    service = make_service(tmp_path, morning, cache_max_age_seconds=1)
    asyncio.run(service.refresh_once())

    service.now_provider = lambda: datetime.fromisoformat("2026-07-04T18:05:00+02:00")

    assert service.effective_status() == "ok"
    assert service.status_code() == 0
    assert service.safe_current_value() == 0.058


def test_tomorrow_payload_keeps_existing_today_active_until_midnight(tmp_path, monkeypatch):
    service = make_service(tmp_path, datetime.fromisoformat("2026-07-04T08:05:00+02:00"))
    patch_response(monkeypatch, make_day_payload("2026-07-04", value_base=0.04))
    asyncio.run(service.refresh_once())

    service.now_provider = lambda: datetime.fromisoformat("2026-07-04T17:05:00+02:00")
    patch_response(monkeypatch, make_day_payload("2026-07-05", value_base=0.08))
    state = asyncio.run(service.refresh_once())

    assert state.status == "ok"
    assert service.current_day()["tariff_date"] == "2026-07-04"
    assert service.tomorrow_day()["tariff_date"] == "2026-07-05"
    assert service.safe_current_value() == 0.057


def test_midnight_rollover_uses_stored_tomorrow_without_poll(tmp_path, monkeypatch):
    service = make_service(tmp_path, datetime.fromisoformat("2026-07-04T17:05:00+02:00"))
    patch_response(monkeypatch, make_day_payload("2026-07-04", value_base=0.04))
    asyncio.run(service.refresh_once())
    patch_response(monkeypatch, make_day_payload("2026-07-05", value_base=0.08))
    asyncio.run(service.refresh_once())

    service.now_provider = lambda: datetime.fromisoformat("2026-07-05T00:05:00+02:00")

    assert service.effective_status() == "ok"
    assert service.current_day()["tariff_date"] == "2026-07-05"
    assert service.safe_current_value() == 0.08


def test_missing_tomorrow_at_midnight_blocks_no_data(tmp_path, monkeypatch):
    service = make_service(tmp_path, datetime.fromisoformat("2026-07-04T17:05:00+02:00"))
    patch_response(monkeypatch, make_day_payload("2026-07-04"))
    asyncio.run(service.refresh_once())

    service.now_provider = lambda: datetime.fromisoformat("2026-07-05T00:05:00+02:00")

    assert service.effective_status() == "no_data"
    assert service.status_code() == 1
    assert service.safe_current_value() is None


def test_single_bad_hour_is_zero_filled_and_keeps_values_available(tmp_path, monkeypatch):
    patch_response(monkeypatch, make_day_payload("2026-07-04", missing=1))
    service = make_service(tmp_path, datetime.fromisoformat("2026-07-04T08:05:00+02:00"))

    state = asyncio.run(service.refresh_once())

    assert state.status == "single_missing_hour_zero_filled"
    assert service.status_code() == 10
    assert service.safe_current_value() == 0.048
    current_day = service.current_day()
    assert current_day is not None
    assert current_day["missing_hours"] == [23]
    assert current_day["zero_filled_hours"] == [23]
    assert service.day_hour_value(23) == 0.0
    assert service.safe_day_hour_value(23) == 0.0
    assert service.day_hour_value(8) == 0.048


def test_duplicate_drop_day_fails_closed_through_effective_status(tmp_path):
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    payload = make_day_payload("2026-07-04")
    duplicate = dict(payload["prices"][56])
    duplicate["feed_in"] = [dict(payload["prices"][56]["feed_in"][0])]
    payload["prices"][57] = duplicate
    day = normalize_bkw_payload(payload, now=now)["day"]
    service = make_service(tmp_path, now)
    service.state.normalized = {"days": {"2026-07-04": day}}

    assert day["duplicate_hours"] == [14]
    assert service.effective_status() == "partial_horizon"
    assert service.status_code() == 4
    assert service.safe_day_hour_value(14) is None


def test_cache_without_duplicate_metadata_fails_closed(tmp_path):
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    day = normalize_bkw_payload(make_day_payload("2026-07-04"), now=now)["day"]
    day.pop("duplicate_hours")
    day.pop("duplicate_interval_count")
    service = make_service(tmp_path, now)
    service.state.normalized = {"days": {"2026-07-04": day}}

    assert service.effective_status() == "partial_horizon"
    assert service.status_code() == 4
    assert service.safe_day_hour_value(14) is None


def test_inconsistent_cached_zero_fill_fails_closed(tmp_path):
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    service = make_service(tmp_path, now)
    day = normalize_bkw_payload(make_day_payload("2026-07-04"), now=now)["day"]
    day["hours"][14] = {
        "hour": 14,
        "value_chf_kwh": 0.0,
        "value_mchf_kwh": 0,
        "interval_count": 0,
        "dst_placeholder": False,
        "zero_filled": True,
    }
    day["hours"][15] = {
        "hour": 15,
        "value_chf_kwh": None,
        "value_mchf_kwh": None,
        "interval_count": 0,
        "dst_placeholder": False,
        "zero_filled": False,
    }
    day.update(
        {
            "received_intervals": 88,
            "missing_hours": [14, 15],
            "missing_hour": None,
            "missing_hour_count": 2,
            "zero_filled_hours": [14],
            "data_quality_status": "partial_horizon",
            "status_code": 4,
        }
    )
    service.state.normalized = {"days": {"2026-07-04": day}}

    assert service.effective_status() == "partial_horizon"
    assert service.status_code() == 4
    assert service.safe_day_hour_value(14) is None
    assert service.safe_day_hour_value(15) is None


def test_zero_fill_marker_without_zero_filled_hour_fails_closed(tmp_path):
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    service = make_service(tmp_path, now)
    day = normalize_bkw_payload(make_day_payload("2026-07-04"), now=now)["day"]
    day.update(
        {
            "missing_hours": [14],
            "missing_hour": 14,
            "missing_hour_count": 1,
            "zero_filled_hours": [14],
            "data_quality_status": "single_missing_hour_zero_filled",
            "status_code": 10,
        }
    )
    service.state.normalized = {"days": {"2026-07-04": day}}

    assert service.effective_status() == "partial_horizon"
    assert service.status_code() == 4
    assert service.safe_day_hour_value(14) is None


def test_zero_filled_hour_with_nonzero_value_fails_closed(tmp_path):
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    service = make_service(tmp_path, now)
    day = normalize_bkw_payload(make_day_payload("2026-07-04", missing=1), now=now)["day"]
    day["hours"][23]["value_chf_kwh"] = 0.023
    day["hours"][23]["value_mchf_kwh"] = 23
    service.state.normalized = {"days": {"2026-07-04": day}}

    assert service.effective_status() == "partial_horizon"
    assert service.status_code() == 4
    assert service.safe_day_hour_value(23) is None


def test_conflicting_missing_hour_metadata_fails_closed(tmp_path):
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    service = make_service(tmp_path, now)
    day = normalize_bkw_payload(make_day_payload("2026-07-04", missing=1), now=now)["day"]
    assert day["zero_filled_hours"] == [23]
    day["missing_hour"] = 22
    service.state.normalized = {"days": {"2026-07-04": day}}

    assert service.effective_status() == "partial_horizon"
    assert service.status_code() == 4
    assert service.safe_day_hour_value(23) is None


def test_api_error_after_valid_today_keeps_today_ok_until_midnight(tmp_path, monkeypatch):
    service = make_service(tmp_path, datetime.fromisoformat("2026-07-04T08:05:00+02:00"))
    patch_response(monkeypatch, make_day_payload("2026-07-04"))
    asyncio.run(service.refresh_once())

    monkeypatch.setattr(
        "bkw_tariff_proxy.service.httpx.AsyncClient",
        lambda **kwargs: RaisingAsyncClient(httpx.ConnectError("boom")),
    )
    service.now_provider = lambda: datetime.fromisoformat("2026-07-04T18:05:00+02:00")
    state = asyncio.run(service.refresh_once())

    assert state.status == "ok"
    assert state.last_error == "boom"
    assert service.status_code() == 0
    assert service.safe_current_value() == 0.058


def test_unknown_unit_blocks(tmp_path, monkeypatch):
    patch_response(monkeypatch, make_day_payload("2026-07-04", unit="mystery"))
    service = make_service(tmp_path, datetime.fromisoformat("2026-07-04T08:05:00+02:00"))

    state = asyncio.run(service.refresh_once())

    assert state.status == "unit_unknown"
    assert service.status_code() == 5
    assert service.safe_current_value() is None


def test_synthetic_test_mode_returns_complete_day_without_http(tmp_path, monkeypatch):
    class FailingClient:
        def __init__(self, **kwargs):
            raise AssertionError("synthetic test mode must not call BKW HTTP endpoint")

    monkeypatch.setattr("bkw_tariff_proxy.service.httpx.AsyncClient", FailingClient)
    service = make_service(tmp_path, datetime.fromisoformat("2026-07-04T08:05:00+02:00"), test_data_mode="synthetic")

    state = asyncio.run(service.refresh_once())

    assert state.status == "ok"
    assert state.last_http_status is None
    assert state.last_error is None
    assert service.current_day()["tariff_date"] == "2026-07-04"
    assert len(service.current_day()["hours"]) == 24
    assert service.status_code() == 0
    cache = json.loads(Path(tmp_path, "cache.json").read_text())
    assert cache["status"] == "ok"

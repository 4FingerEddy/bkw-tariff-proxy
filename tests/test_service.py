import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from bkw_tariff_proxy.config import Settings
from bkw_tariff_proxy.service import TariffService


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
        "data_dir": str(tmp_path),
        "timezone": "Europe/Zurich",
        "require_full_horizon": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_quarter_hour_payload(now: datetime, *, hours: int = 24, missing_last_quarters: int = 0, publication_timestamp: str | None = None):
    base = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    prices = []
    total_intervals = hours * 4 - missing_last_quarters
    for index in range(total_intervals):
        start = base + timedelta(minutes=15 * index)
        prices.append(
            {
                "start_timestamp": start.isoformat(),
                "end_timestamp": (start + timedelta(minutes=15)).isoformat(),
                "feed_in": [{"unit": "CHF_kWh", "value": 0.08 + (index % 4) / 1000}],
            }
        )
    return {
        "publication_timestamp": publication_timestamp or now.astimezone(timezone.utc).isoformat(),
        "prices": prices,
    }


def test_bkw_404_is_no_data_and_persisted(tmp_path, monkeypatch):
    response = httpx.Response(404, request=httpx.Request("GET", "https://example.invalid/tariffs"))
    monkeypatch.setattr("bkw_tariff_proxy.service.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient(response))
    service = TariffService(make_settings(tmp_path))

    state = asyncio.run(service.refresh_once())

    assert state.status == "no_data"
    assert state.last_http_status == 404
    assert "404" in state.last_error
    cache = json.loads(Path(tmp_path, "cache.json").read_text())
    assert cache["status"] == "no_data"


def test_loaded_cache_older_than_max_age_is_reported_stale(tmp_path):
    old_update = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    Path(tmp_path, "cache.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "normalized": {"status": "ok", "relative": [{"offset": 0, "value": 0.081}]},
                "updated_at": old_update,
                "last_error": None,
                "last_http_status": 200,
            }
        )
    )

    service = TariffService(make_settings(tmp_path, cache_max_age_seconds=60))

    assert service.effective_status() == "stale"
    assert service.status_code() == 2


def test_publication_timestamp_can_be_older_than_fetch_without_forcing_stale(tmp_path):
    now = datetime.now(timezone.utc)
    service = TariffService(make_settings(tmp_path, cache_max_age_seconds=60))
    service.state.status = "ok"
    service.state.updated_at = now.isoformat()
    service.state.normalized = {
        "status": "ok",
        "publication_timestamp": (now - timedelta(hours=12)).isoformat(),
        "relative": [{"offset": 0, "value": 0.081}],
    }

    assert service.effective_status() == "ok"
    assert service.status_code() == 0


def test_relative_value_returns_none_for_missing_offset(tmp_path):
    service = TariffService(make_settings(tmp_path))
    service.state.normalized = {"relative": [{"offset": 1, "value": 0.077}]}

    assert service.relative_value(0) is None
    assert service.relative_value(1) == 0.077


def test_safe_relative_value_requires_effective_ok_status(tmp_path):
    service = TariffService(make_settings(tmp_path))
    service.state.status = "api_error"
    service.state.normalized = {"relative": [{"offset": 0, "value": 0.081}]}

    assert service.relative_value(0) == 0.081
    assert service.safe_relative_value(0) is None


def test_synthetic_test_mode_returns_full_loxone_horizon_without_http(tmp_path, monkeypatch):
    class FailingClient:
        def __init__(self, **kwargs):
            raise AssertionError("synthetic test mode must not call BKW HTTP endpoint")

    monkeypatch.setattr("bkw_tariff_proxy.service.httpx.AsyncClient", FailingClient)
    service = TariffService(make_settings(tmp_path, test_data_mode="synthetic", require_full_horizon=True))

    state = asyncio.run(service.refresh_once())

    assert state.status == "ok"
    assert state.last_http_status is None
    assert state.last_error is None
    assert state.normalized["horizon_hours"] == 24
    assert [slot["offset"] for slot in state.normalized["relative"]] == list(range(24))
    assert service.status_code() == 0
    assert service.relative_value(0) is not None
    cache = json.loads(Path(tmp_path, "cache.json").read_text())
    assert cache["status"] == "ok"


def test_live_full_horizon_requires_complete_quarter_hours(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).replace(minute=5, second=0, microsecond=0)
    payload = make_quarter_hour_payload(now, hours=24, missing_last_quarters=3)
    response = httpx.Response(200, json=payload, request=httpx.Request("GET", "https://example.invalid/tariffs"))
    monkeypatch.setattr("bkw_tariff_proxy.service.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient(response))
    service = TariffService(make_settings(tmp_path, require_full_horizon=True))

    state = asyncio.run(service.refresh_once())

    assert state.status == "partial_horizon"
    assert service.status_code() == 4
    assert state.normalized["horizon_hours"] == 24
    assert state.normalized["min_interval_count"] == 1


def test_live_complete_quarter_hour_horizon_is_ok(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    payload = make_quarter_hour_payload(now, hours=24)
    response = httpx.Response(200, json=payload, request=httpx.Request("GET", "https://example.invalid/tariffs"))
    monkeypatch.setattr("bkw_tariff_proxy.service.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient(response))
    service = TariffService(make_settings(tmp_path, require_full_horizon=True))

    state = asyncio.run(service.refresh_once())

    assert state.status == "ok"
    assert service.status_code() == 0
    assert state.normalized["horizon_hours"] == 24
    assert state.normalized["min_interval_count"] == 4


def test_api_error_preserves_cache_but_safe_value_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "bkw_tariff_proxy.service.httpx.AsyncClient",
        lambda **kwargs: RaisingAsyncClient(httpx.ConnectError("boom")),
    )
    service = TariffService(make_settings(tmp_path))
    service.state.normalized = {"relative": [{"offset": 0, "value": 0.081}]}

    state = asyncio.run(service.refresh_once())

    assert state.status == "api_error"
    assert service.relative_value(0) == 0.081
    assert service.safe_relative_value(0) is None

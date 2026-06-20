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


def test_relative_value_returns_none_for_missing_offset(tmp_path):
    service = TariffService(make_settings(tmp_path))
    service.state.normalized = {"relative": [{"offset": 1, "value": 0.077}]}

    assert service.relative_value(0) is None
    assert service.relative_value(1) == 0.077

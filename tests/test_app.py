from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from bkw_tariff_proxy import main
from bkw_tariff_proxy.service import TariffState

TZ = ZoneInfo("Europe/Zurich")
client = TestClient(main.app)


def day(day_str: str, *, base: float = 0.04):
    hours = []
    for hour in range(24):
        value = round(base + hour / 1000, 6)
        hours.append(
            {
                "hour": hour,
                "value_chf_kwh": value,
                "value_mchf_kwh": int(round(value * 1000)),
                "interval_count": 4,
                "dst_placeholder": False,
            }
        )
    local_start = datetime.fromisoformat(day_str).replace(tzinfo=TZ)
    return {
        "tariff_date": day_str,
        "timezone": "Europe/Zurich",
        "hours": hours,
        "coverage_start_utc": local_start.astimezone(ZoneInfo("UTC")).isoformat(),
        "coverage_end_utc": (local_start + timedelta(days=1)).astimezone(ZoneInfo("UTC")).isoformat(),
        "expected_intervals": 96,
        "received_intervals": 96,
        "content_hash": f"hash-{day_str}",
        "publication_timestamp": f"{day_str}T12:00:00Z",
    }


def set_state(state: TariffState, now: datetime | None = None):
    main.service.state = state
    if now:
        main.service.now_provider = lambda: now


def ok_state(now: datetime):
    today = now.astimezone(TZ).date().isoformat()
    return TariffState(
        status="ok",
        normalized={"status": "ok", "unit": "CHF/kWh", "days": {today: day(today)}},
        updated_at=now.isoformat(),
        upstream_last_success_at=now.isoformat(),
        last_error=None,
        last_http_status=200,
    )


def test_health_returns_plain_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "ok"


def test_relative_endpoint_returns_plain_number_when_status_ok():
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    set_state(ok_state(now), now)

    response = client.get("/v1/feedin/relative/0")

    assert response.status_code == 200
    assert response.text == "0.048000"


def test_relative_endpoint_blocks_cached_value_when_status_not_ok():
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    state = ok_state(now)
    state.status = "api_error"
    state.normalized["days"] = {}
    set_state(state, now)

    response = client.get("/v1/feedin/relative/0")

    assert response.status_code == 503
    assert "status is api_error" in response.text or "status is no_data" in response.text


def test_missing_relative_endpoint_returns_503_not_zero():
    now = datetime.fromisoformat("2026-07-05T00:05:00+02:00")
    yesterday = "2026-07-04"
    set_state(TariffState(status="ok", normalized={"days": {yesterday: day(yesterday)}}), now)

    response = client.get("/v1/feedin/relative/0")

    assert response.status_code == 503
    assert "status is no_data" in response.text


def test_status_endpoint_uses_day_guard_not_cache_age():
    now = datetime.fromisoformat("2026-07-04T18:05:00+02:00")
    state = ok_state(now)
    state.updated_at = datetime.fromisoformat("2026-07-04T08:05:00+02:00").isoformat()
    set_state(state, now)

    assert client.get("/v1/status").text == "ok"
    assert client.get("/v1/status-code").text == "0"


def test_status_endpoint_blocks_wrong_day_data():
    now = datetime.fromisoformat("2026-07-05T00:05:00+02:00")
    set_state(TariffState(status="ok", normalized={"days": {"2026-07-04": day("2026-07-04")}}), now)

    assert client.get("/v1/status").text == "no_data"
    assert client.get("/v1/status-code").text == "1"


def test_relative_json_exposes_diagnostic_status():
    now = datetime.fromisoformat("2026-07-04T17:05:00+02:00")
    set_state(ok_state(now), now)

    response = client.get("/v1/feedin/relative.json")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["status_code"] == 0
    assert payload["effective_status"] == "ok"
    assert payload["effective_status_code"] == 0
    assert payload["safe_values_available"] is True
    assert payload["diagnostic_only"] is True
    assert payload["horizon_hours"] == 7
    assert payload["relative"][0]["offset"] == 0


def test_current_endpoint_blocks_when_status_not_ok():
    now = datetime.fromisoformat("2026-07-05T00:05:00+02:00")
    set_state(TariffState(status="ok", normalized={"days": {"2026-07-04": day("2026-07-04")}}), now)

    response = client.get("/v1/feedin/current")

    assert response.status_code == 503
    assert "status is no_data" in response.text


def test_current_and_status_endpoint_is_loxone_friendly():
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    set_state(ok_state(now), now)

    response = client.get("/v1/feedin/current-and-status")

    assert response.status_code == 200
    assert response.text == "0;0.048000"


def test_index_exposes_flat_absolute_loxone_template_fields():
    now = datetime.fromisoformat("2026-07-04T08:05:00+02:00")
    set_state(ok_state(now), now)

    response = client.get("/")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status_code"] == 0
    assert payload["tariff_date"] == "2026-07-04"
    assert payload["feedin_current"] == 0.048
    assert payload["feedin_current_mchf_kwh"] == 48
    assert payload["feedin_h00"] == 0.04
    assert payload["feedin_h00_mchf_kwh"] == 40
    assert payload["feedin_h23"] == 0.063
    assert payload["feedin_h23_mchf_kwh"] == 63
    assert "feedin_relative_00" not in payload
    assert payload["loxone_integer_scale"] == "milli-CHF/kWh; divide by 1000 for CHF/kWh display"
    assert "Absolut" in payload["template_hint"]


def test_index_keeps_status_but_nulls_tariff_values_when_not_ok():
    now = datetime.fromisoformat("2026-07-05T00:05:00+02:00")
    set_state(TariffState(status="ok", normalized={"days": {"2026-07-04": day("2026-07-04")}}), now)

    response = client.get("/")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "no_data"
    assert payload["status_code"] == 1
    assert payload["feedin_current"] is None
    assert payload["feedin_current_mchf_kwh"] is None
    assert payload["feedin_h00"] is None
    assert payload["feedin_h00_mchf_kwh"] is None

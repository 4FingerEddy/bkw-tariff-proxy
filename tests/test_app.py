from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from bkw_tariff_proxy import main
from bkw_tariff_proxy.service import TariffState


client = TestClient(main.app)


def set_state(state: TariffState):
    main.service.state = state


def test_health_returns_plain_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "ok"


def test_relative_endpoint_returns_plain_number_when_status_ok():
    set_state(
        TariffState(
            status="ok",
            normalized={"relative": [{"offset": 0, "value": 0.081}]},
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error=None,
            last_http_status=200,
        )
    )

    response = client.get("/v1/feedin/relative/0")

    assert response.status_code == 200
    assert response.text == "0.081000"


def test_relative_endpoint_blocks_cached_value_when_status_not_ok():
    set_state(
        TariffState(
            status="api_error",
            normalized={"relative": [{"offset": 0, "value": 0.081}]},
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error="upstream timeout",
            last_http_status=None,
        )
    )

    response = client.get("/v1/feedin/relative/0")

    assert response.status_code == 503
    assert "status is api_error" in response.text


def test_missing_relative_endpoint_returns_503_not_zero():
    set_state(TariffState(status="no_data", normalized={"relative": []}))

    response = client.get("/v1/feedin/relative/0")

    assert response.status_code == 503
    assert "status is no_data" in response.text


def test_status_endpoint_uses_effective_stale_status():
    set_state(
        TariffState(
            status="ok",
            normalized={"relative": [{"offset": 0, "value": 0.081}]},
            updated_at=(datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
            last_error=None,
            last_http_status=200,
        )
    )

    assert client.get("/v1/status").text == "stale"
    assert client.get("/v1/status-code").text == "2"


def test_relative_json_exposes_source_and_effective_status():
    set_state(
        TariffState(
            status="partial_horizon",
            normalized={
                "status": "ok",
                "unit": "CHF/kWh",
                "horizon_hours": 17,
                "relative": [{"offset": 7, "value": 0.105}],
            },
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error=None,
            last_http_status=200,
        )
    )

    response = client.get("/v1/feedin/relative.json")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "partial_horizon"
    assert payload["status_code"] == 4
    assert payload["effective_status"] == "partial_horizon"
    assert payload["effective_status_code"] == 4
    assert payload["source_status"] == "partial_horizon"
    assert payload["normalized_status"] == "ok"
    assert payload["safe_values_available"] is False
    assert payload["horizon_hours"] == 17
    assert payload["relative"] == [{"offset": 7, "value": 0.105}]


def test_relative_json_marks_safe_values_available_when_effective_ok():
    set_state(
        TariffState(
            status="ok",
            normalized={
                "status": "ok",
                "unit": "CHF/kWh",
                "horizon_hours": 24,
                "relative": [{"offset": 0, "value": 0.081}],
            },
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error=None,
            last_http_status=200,
        )
    )

    payload = client.get("/v1/feedin/relative.json").json()

    assert payload["status"] == "ok"
    assert payload["status_code"] == 0
    assert payload["safe_values_available"] is True


def test_current_endpoint_blocks_cached_value_when_status_not_ok():
    set_state(
        TariffState(
            status="api_error",
            normalized={"relative": [{"offset": 0, "value": 0.081}]},
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error="upstream timeout",
            last_http_status=None,
        )
    )

    response = client.get("/v1/feedin/current")

    assert response.status_code == 503
    assert "status is api_error" in response.text


def test_current_and_status_endpoint_is_loxone_friendly():
    set_state(
        TariffState(
            status="ok",
            normalized={"relative": [{"offset": 0, "value": 0.081}]},
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error=None,
            last_http_status=200,
        )
    )

    response = client.get("/v1/feedin/current-and-status")

    assert response.status_code == 200
    assert response.text == "0;0.081000"


def test_current_and_status_blocks_cached_value_when_status_not_ok():
    set_state(
        TariffState(
            status="api_error",
            normalized={"relative": [{"offset": 0, "value": 0.081}]},
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error="upstream timeout",
            last_http_status=None,
        )
    )

    response = client.get("/v1/feedin/current-and-status")

    assert response.status_code == 503
    assert "status is api_error" in response.text


def test_index_exposes_flat_loxone_template_fields():
    set_state(
        TariffState(
            status="ok",
            normalized={
                "unit": "CHF/kWh",
                "horizon_hours": 2,
                "relative": [
                    {"offset": 0, "value": 0.081},
                    {"offset": 1, "value": 0.077},
                ],
            },
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error=None,
            last_http_status=200,
        )
    )

    response = client.get("/")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status_code"] == 0
    assert payload["feedin_current"] == 0.081
    assert payload["feedin_current_mchf_kwh"] == 81
    assert payload["feedin_relative_00"] == 0.081
    assert payload["feedin_relative_00_mchf_kwh"] == 81
    assert payload["feedin_relative_01"] == 0.077
    assert payload["feedin_relative_01_mchf_kwh"] == 77
    assert payload["feedin_relative_23"] is None
    assert payload["feedin_relative_23_mchf_kwh"] is None
    assert payload["loxone_integer_scale"] == "milli-CHF/kWh; divide by 1000 for CHF/kWh display"
    assert payload["template_hint"] == "Loxone command recognitions should use *_mchf_kwh integer keys to avoid decimal separator parsing issues."


def test_index_keeps_status_but_nulls_cached_tariff_values_when_not_ok():
    set_state(
        TariffState(
            status="api_error",
            normalized={
                "unit": "CHF/kWh",
                "horizon_hours": 24,
                "relative": [
                    {"offset": 0, "value": 0.081},
                    {"offset": 1, "value": 0.077},
                ],
            },
            updated_at=datetime.now(timezone.utc).isoformat(),
            last_error="upstream timeout",
            last_http_status=None,
        )
    )

    response = client.get("/")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "api_error"
    assert payload["status_code"] == 3
    assert payload["feedin_current"] is None
    assert payload["feedin_current_mchf_kwh"] is None
    assert payload["feedin_relative_00"] is None
    assert payload["feedin_relative_00_mchf_kwh"] is None

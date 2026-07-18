from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response

from .config import Settings
from .normalizer import value_to_mchf_kwh
from .service import TariffService

settings = Settings()
service = TariffService(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await service.refresh_once()

    async def poll_loop() -> None:
        while True:
            await asyncio.sleep(settings.poll_interval_seconds)
            await service.refresh_once()

    task = asyncio.create_task(poll_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="BKW Tariff Proxy", version="0.2.0", lifespan=lifespan)


@app.get("/health", response_class=Response)
def health() -> str:
    return "ok"


@app.get("/v1/status", response_class=Response)
def status() -> str:
    return service.effective_status()


@app.get("/v1/status-code", response_class=Response)
def status_code() -> str:
    return str(service.status_code())


@app.get("/v1/feedin/relative.json")
def relative_json() -> dict:
    """Return diagnostic rolling tariff data.

    Productive Loxone values live in `/v1/loxone.json` as absolute local day
    fields `feedin_h00...feedin_h23`. This endpoint is diagnostic only.
    """

    effective_status = service.effective_status()
    upstream_age = service.upstream_age_seconds()
    payload = {
        **service.state.normalized,
        "source_status": service.state.status,
        "effective_status": effective_status,
        "effective_status_code": service.status_code(),
        "status": effective_status,
        "status_code": service.status_code(),
        "safe_values_available": effective_status in {"ok", "single_missing_hour_zero_filled"},
        "diagnostic_only": True,
        "updated_at": service.state.updated_at,
        "upstream_status": "ok" if service.state.last_error is None else "error",
        "upstream_age_seconds": upstream_age,
        "last_error": service.state.last_error,
        "last_http_status": service.state.last_http_status,
    }
    return payload


@app.get("/v1/feedin/current", response_class=Response)
def current() -> str:
    value = service.safe_current_value()
    if value is None:
        raise HTTPException(status_code=503, detail=f"status is {service.effective_status()}; no valid current feed-in value")
    return f"{value:.6f}"


@app.get("/v1/feedin/current-and-status", response_class=Response)
def current_and_status() -> str:
    value = service.safe_current_value()
    if value is None:
        raise HTTPException(status_code=503, detail=f"status is {service.effective_status()}; no valid current feed-in value")
    return f"{service.status_code()};{value:.6f}"


@app.get("/v1/feedin/relative/{offset}", response_class=Response)
def relative(offset: int) -> str:
    if offset < 0 or offset > 23:
        raise HTTPException(status_code=404, detail="offset must be 0..23")
    value = service.safe_relative_value(offset)
    if value is None:
        raise HTTPException(status_code=503, detail=f"status is {service.effective_status()}; no valid feed-in value for offset {offset}")
    return f"{value:.6f}"


def loxone_template_payload() -> dict:
    effective_status = service.effective_status()
    current_value = service.safe_current_value()
    today = service.current_day()
    upstream_age = service.upstream_age_seconds()
    payload = {
        "service": "bkw-tariff-proxy",
        "status": effective_status,
        "status_code": service.status_code(),
        "updated_at": service.state.updated_at,
        "unit": service.state.normalized.get("unit", "CHF/kWh"),
        "tariff_date": today.get("tariff_date") if today else None,
        "day_today_status": service.state.normalized.get("day_today_status"),
        "day_tomorrow_status": service.state.normalized.get("day_tomorrow_status"),
        "data_quality_status": service.state.normalized.get("data_quality_status"),
        "missing_hours": service.state.normalized.get("missing_hours", []),
        "missing_hour": service.state.normalized.get("missing_hour"),
        "missing_hour_count": service.state.normalized.get("missing_hour_count", 0),
        "zero_filled_hours": service.state.normalized.get("zero_filled_hours", []),
        "upstream_status": "ok" if service.state.last_error is None else "error",
        "upstream_age_seconds": upstream_age,
        "feedin_current": current_value,
        "feedin_current_mchf_kwh": value_to_mchf_kwh(current_value),
        "loxone_integer_scale": "milli-CHF/kWh; divide by 1000 for CHF/kWh display",
        "template_hint": "Use feedin_h00_mchf_kwh..feedin_h23_mchf_kwh with Spotpreis-Optimierer in Absolut mode.",
    }
    for hour in range(24):
        value = service.safe_day_hour_value(hour)
        payload[f"feedin_h{hour:02d}"] = value
        payload[f"feedin_h{hour:02d}_mchf_kwh"] = value_to_mchf_kwh(value)
    return payload


@app.get("/v1/loxone.json")
def loxone_json() -> dict:
    return loxone_template_payload()


@app.get("/")
def index() -> dict:
    return loxone_template_payload()

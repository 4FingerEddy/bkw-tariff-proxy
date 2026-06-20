from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response

from .config import Settings
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


app = FastAPI(title="BKW Tariff Proxy", version="0.1.0", lifespan=lifespan)


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
    return {
        "status": service.state.status,
        "updated_at": service.state.updated_at,
        "last_error": service.state.last_error,
        **service.state.normalized,
    }


@app.get("/v1/feedin/current", response_class=Response)
def current() -> str:
    return relative(0)


@app.get("/v1/feedin/current-and-status", response_class=Response)
def current_and_status() -> str:
    value = service.relative_value(0)
    if value is None:
        raise HTTPException(status_code=503, detail="no valid current feed-in value")
    return f"{service.status_code()};{value:.6f}"


@app.get("/v1/feedin/relative/{offset}", response_class=Response)
def relative(offset: int) -> str:
    if offset < 0 or offset > 23:
        raise HTTPException(status_code=404, detail="offset must be 0..23")
    value = service.relative_value(offset)
    if value is None:
        raise HTTPException(status_code=503, detail=f"no valid feed-in value for offset {offset}")
    return f"{value:.6f}"


def loxone_template_payload() -> dict:
    payload = {
        "service": "bkw-tariff-proxy",
        "status": service.effective_status(),
        "status_code": service.status_code(),
        "updated_at": service.state.updated_at,
        "unit": service.state.normalized.get("unit", "CHF/kWh"),
        "horizon_hours": service.state.normalized.get("horizon_hours", 0),
        "feedin_current": service.relative_value(0),
        "template_hint": "Loxone virtual HTTP input command recognitions can parse these flat keys.",
        "loxone_relative_endpoints": [f"/v1/feedin/relative/{i}" for i in range(24)],
    }
    for offset in range(24):
        payload[f"feedin_relative_{offset:02d}"] = service.relative_value(offset)
    return payload


@app.get("/v1/loxone.json")
def loxone_json() -> dict:
    return loxone_template_payload()


@app.get("/")
def index() -> dict:
    return loxone_template_payload()

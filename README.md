# bkw-tariff-proxy

HTTP proxy for BKW dynamic feed-in tariffs and Loxone virtual HTTP inputs.

The service polls BKW's dynamic feed-in tariff endpoint, caches the result locally, normalizes quarter-hour values into Loxone-friendly hourly relative slots, and exposes simple HTTP endpoints for Loxone command recognitions.

## Features

- FastAPI HTTP service packaged as a Docker container.
- Local cache under `/data` so short upstream outages do not immediately break reads.
- BKW `feed_in` values normalized to `CHF/kWh`.
- Hourly relative slots `+0 ... +23` computed as the arithmetic mean of available quarter-hour values inside each hour.
- Integer `mCHF/kWh` fields for Loxone, avoiding decimal separator parsing issues.
- Numeric status code for simple Loxone guard logic.
- Non-root container user and Docker healthcheck.
- Optional synthetic test mode for Loxone wiring tests.

## Container image

Recommended image name after release:

```text
ghcr.io/4fingereddy/bkw-tariff-proxy:<version>
```

Example:

```bash
docker run -d \
  --name bkw-tariff-proxy \
  --restart unless-stopped \
  -p 8785:8785 \
  -v bkw-tariff-proxy-data:/data \
  ghcr.io/4fingereddy/bkw-tariff-proxy:0.1.0
```

## Docker Compose

```yaml
services:
  bkw-tariff-proxy:
    image: ghcr.io/4fingereddy/bkw-tariff-proxy:0.1.0
    container_name: bkw-tariff-proxy
    restart: unless-stopped
    ports:
      - "8785:8785"
    environment:
      TZ: Europe/Zurich
      DATA_DIR: /data
      BKW_ENDPOINT: https://api.bkw.ch/api/dyntariffs/v1/Tariffs/energyreturn
      POLL_INTERVAL_SECONDS: "900"
      CACHE_MAX_AGE_SECONDS: "5400"
      REQUIRE_FULL_HORIZON: "true"
      BKW_TEST_DATA_MODE: "off"
    volumes:
      - bkw-tariff-proxy-data:/data

volumes:
  bkw-tariff-proxy-data:
```

## Configuration

Environment variables:

- `BKW_ENDPOINT`: BKW tariff endpoint. Default: `https://api.bkw.ch/api/dyntariffs/v1/Tariffs/energyreturn`.
- `POLL_INTERVAL_SECONDS`: background polling interval. Default: `900`.
- `CACHE_MAX_AGE_SECONDS`: maximum age for cached `ok` data before reporting `stale`. Default: `5400`.
- `DATA_DIR`: cache directory inside the container. Default: `/data`.
- `TZ`: timezone used by the container. Default: `Europe/Zurich`.
- `REQUIRE_FULL_HORIZON`: when true, report `partial_horizon` unless 24 hourly slots are available and live BKW quarter-hour data has all 4 intervals per hour. Default: `true`.
- `BKW_TEST_DATA_MODE`: set to `synthetic` only for lab/Loxone wiring tests. Production should use `off` or omit the variable.

## Endpoints

- `GET /health` → `ok`
- `GET /` → flat Loxone JSON payload
- `GET /v1/loxone.json` → same flat Loxone JSON payload
- `GET /v1/status` → text status
- `GET /v1/status-code` → numeric status for Loxone logic
- `GET /v1/feedin/current` → current `+0` value in `CHF/kWh`, or HTTP 503 if unavailable or status is not `ok`
- `GET /v1/feedin/current-and-status` → `status_code;value`, for example `0;0.081000`; HTTP 503 unless status is `ok`
- `GET /v1/feedin/relative/{offset}` → `CHF/kWh` value for offset `0 ... 23`, or HTTP 503 if unavailable or status is not `ok`
- `GET /v1/feedin/relative.json` → normalized debug JSON; may include cached values even when status is degraded

## Loxone JSON fields

The flat root payload contains:

```text
status
status_code
updated_at
unit
horizon_hours
feedin_current
feedin_current_mchf_kwh
feedin_relative_00 ... feedin_relative_23
feedin_relative_00_mchf_kwh ... feedin_relative_23_mchf_kwh
```

For Loxone command recognitions, prefer the integer fields:

```text
status-code -> \i"status_code":\i\v
current     -> \i"feedin_current_mchf_kwh":\i\v
+0          -> \i"feedin_relative_00_mchf_kwh":\i\v
+1          -> \i"feedin_relative_01_mchf_kwh":\i\v
+23         -> \i"feedin_relative_23_mchf_kwh":\i\v
```

Scale:

```text
45 = 0.045 CHF/kWh
factor for CHF/kWh display = 0.001
```

## Status codes

- `0`: OK — data valid and full horizon available.
- `1`: No data — BKW returned no usable tariff data.
- `2`: Stale — last valid data is too old.
- `3`: API error — upstream request or processing failed.
- `4`: Partial horizon — data exists, but fewer than 24 hourly slots are available.
- `5`: Unknown unit — upstream unit is not safely understood.
- `99`: Unknown internal state.

Recommended Loxone guard:

```text
status_code == 0 -> optimizer may use values; tariff fields are populated
status_code != 0 -> block/neutralize optimization; flat Loxone tariff fields are intentionally null
```

## Local development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
pytest -q
python -m py_compile src/bkw_tariff_proxy/*.py
```

Run locally:

```bash
DATA_DIR=/tmp/bkw-tariff-proxy-data \
  uvicorn bkw_tariff_proxy.main:app --host 127.0.0.1 --port 8785
```

Smoke check:

```bash
curl http://127.0.0.1:8785/health
curl http://127.0.0.1:8785/v1/status
curl http://127.0.0.1:8785/v1/status-code
curl http://127.0.0.1:8785/v1/loxone.json
```

## Synthetic test mode

For Loxone wiring tests without live BKW dependency:

```yaml
BKW_TEST_DATA_MODE: synthetic
```

Synthetic values are deliberately fake and must not be used for production energy optimization.

## Safety notes

- Do not expose this service directly to the internet.
- Do not treat missing tariff values as zero.
- Do not guess unknown units; fail visibly instead.
- Keep `/data` persistent.
- Configure Loxone to block optimization unless `status_code == 0`.

## License

MIT

# bkw-tariff-proxy

HTTP proxy for BKW dynamic feed-in tariffs and Loxone virtual HTTP inputs.

The service polls BKW's dynamic feed-in tariff endpoint, stores the received Swiss local tariff day, normalizes quarter-hour `feed_in` values into absolute hourly day values, and exposes Loxone-friendly HTTP endpoints.

## Features

- FastAPI HTTP service packaged as a Docker container.
- Local persistent day store under `/data` so same-day tariffs survive upstream outages and container restarts.
- BKW `feed_in` values normalized to `CHF/kWh` and **not inverted**.
- Absolute local day slots `h00 ... h23` for the Loxone Spotpreis-Optimierer in **Absolut** mode.
- Diagnostic rolling relative endpoints only for operators.
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
  ghcr.io/4fingereddy/bkw-tariff-proxy:0.2.0
```

## Docker Compose

```yaml
services:
  bkw-tariff-proxy:
    image: ghcr.io/4fingereddy/bkw-tariff-proxy:0.2.0
    container_name: bkw-tariff-proxy
    restart: unless-stopped
    ports:
      - "8785:8785"
    environment:
      TZ: Europe/Zurich
      DATA_DIR: /data
      BKW_ENDPOINT: https://api.bkw.ch/api/dyntariffs/v1/Tariffs/energyreturn
      POLL_INTERVAL_SECONDS: "900"
      UPSTREAM_WARN_AGE_SECONDS: "7200"
      REQUIRE_COMPLETE_DAY: "true"
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
- `UPSTREAM_WARN_AGE_SECONDS`: age after which upstream health should be considered old for diagnostics. It does **not** invalidate a valid same-day tariff vector.
- `DATA_DIR`: cache directory inside the container. Default: `/data`.
- `TZ`: tariff timezone. Default: `Europe/Zurich`.
- `REQUIRE_COMPLETE_DAY`: when true, the active tariff day must have all expected quarter-hour intervals. Default: `true`.
- `BKW_TEST_DATA_MODE`: set to `synthetic` only for lab/Loxone wiring tests. Production should use `off` or omit the variable.

Legacy `CACHE_MAX_AGE_SECONDS` / `REQUIRE_FULL_HORIZON` are still tolerated as environment fallbacks, but the day-vector model no longer treats same-day prices as stale after 90 minutes.

## Endpoints

- `GET /health` → `ok`
- `GET /` → flat Loxone JSON payload
- `GET /v1/loxone.json` → same flat Loxone JSON payload
- `GET /v1/status` → text status
- `GET /v1/status-code` → numeric status for Loxone logic
- `GET /v1/feedin/current` → current local-hour value in `CHF/kWh`, or HTTP 503 if unavailable or status is not `ok`
- `GET /v1/feedin/current-and-status` → `status_code;value`, for example `0;0.081000`; HTTP 503 unless status is `ok`
- `GET /v1/feedin/relative/{offset}` → diagnostic rolling `CHF/kWh` value for offset `0 ... 23`, or HTTP 503 if unavailable or status is not `ok`
- `GET /v1/feedin/relative.json` → diagnostic relative JSON. Do not wire this into the Spotpreis-Optimierer.

## Loxone JSON fields

The flat root payload contains:

```text
status
status_code
updated_at
unit
tariff_date
day_today_status
day_tomorrow_status
upstream_status
upstream_age_seconds
feedin_current
feedin_current_mchf_kwh
feedin_h00 ... feedin_h23
feedin_h00_mchf_kwh ... feedin_h23_mchf_kwh
```

For Loxone command recognitions, use the integer fields:

```text
status-code -> \i"status_code":\i\v
current     -> \i"feedin_current_mchf_kwh":\i\v
h00         -> \i"feedin_h00_mchf_kwh":\i\v
h01         -> \i"feedin_h01_mchf_kwh":\i\v
h23         -> \i"feedin_h23_mchf_kwh":\i\v
```

Scale:

```text
45 = 0.045 CHF/kWh
factor for CHF/kWh display = 0.001
```

## Status codes

- `0`: OK — complete, validated dataset for today's local tariff date is active.
- `1`: No data — no dataset for today's local tariff date.
- `2`: Stale — defensive guard for wrong-day active data.
- `3`: API error — upstream request or processing failed and no valid today dataset is available.
- `4`: Partial horizon — today's dataset exists, but expected intervals/hours are incomplete.
- `5`: Unknown unit — upstream unit is not safely understood.
- `10`: Single missing hour zero-filled — exactly one incomplete local hour was explicitly replaced with `0`; all other hours passed validation and tariff fields remain populated.
- `99`: Unknown internal state.

Recommended Loxone guard:

```text
status_code == 0  -> optimizer may use the complete validated values
status_code == 10 -> optimizer may use the values; show a data-quality warning for missing_hour
all other codes  -> block/neutralize optimization; flat Loxone tariff fields are null
```

## Loxone target model

Use one parent virtual HTTP input `BKW Dyntariffs` on `/v1/loxone.json` or `/`, and wire the 24 values into the Spotpreis-Optimierer in **Absolut** mode:

```text
BKW h00 -> feedin_h00_mchf_kwh
...
BKW h23 -> feedin_h23_mchf_kwh
```

Do not configure the Spotpreis-Optimierer for relative +0...+23 mode for this BKW integration.

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
- Do not silently treat missing tariff values as zero. Only the explicit single-hour policy may zero-fill exactly one incomplete local hour and must report status code `10` plus `missing_hour`; the resulting `0.0` is fabricated, not a measured tariff.
- Do not consume the plain current/relative value endpoints without the status guard. Use `/v1/feedin/current-and-status` or `/v1/loxone.json` when status and value must stay coupled.
- Do not guess unknown units; fail visibly instead.
- Keep `/data` persistent.
- Configure Loxone to allow optimization only for status codes `0` and `10`; all other codes must block or neutralize it.

## License

MIT

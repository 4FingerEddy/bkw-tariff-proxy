# bkw-tariff-proxy

Docker HTTP service for BKW dynamic feed-in tariffs and Loxone virtual HTTP inputs.

## Product goal

BKW Dynamic Feed-in Tariff → local Docker HTTP service → Loxone Spotpreis-Optimierer in relative mode.

This service polls BKW once, caches the result locally, and exposes simple LAN HTTP endpoints so Loxone does not need to parse complex JSON or talk to BKW directly.

## Current status

Docker/FastAPI MVP is deployed on Synology/Portainer and runs against the live BKW Dynamic Tariffs API.

Observed BKW state:

```text
2026-06-20: Swagger 200 OK, live tariff endpoints 404/no_data
2026-07-02: /Tariffs/energyreturn 200 OK, 96 quarter-hour feed_in intervals, unit CHF_kWh
```

The app still treats BKW 404 as `no_data` for resilience, but normal production operation now expects live tariff data. BKW currently publishes next-day values; before midnight the proxy may report `partial_horizon` because `+0` for the current hour is not yet present.

## Local development

The source lives on the Synology NAS mount:

```text
/mnt/synology-rootkeeper/projects/bkw-tariff-proxy
```

Because the NAS mount does not support the symlinks needed by Python venvs, the development venv is local on the Pi:

```text
/home/rootkeeper/.venvs/bkw-tariff-proxy
```

Run tests:

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy
. /home/rootkeeper/.venvs/bkw-tariff-proxy/bin/activate
pytest -q
python -m py_compile src/bkw_tariff_proxy/*.py
```

Current verification:

```text
17 passed, 1 warning
```

The remaining warning is from FastAPI/Starlette TestClient internals, not from application code.

## Run locally without Docker

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy
DATA_DIR=/tmp/bkw-tariff-proxy-data \
  /home/rootkeeper/.venvs/bkw-tariff-proxy/bin/uvicorn bkw_tariff_proxy.main:app \
  --host 127.0.0.1 \
  --port 8785
```

Smoke check:

```bash
curl http://127.0.0.1:8785/health
curl http://127.0.0.1:8785/v1/status
curl http://127.0.0.1:8785/v1/status-code
curl http://127.0.0.1:8785/v1/feedin/relative.json
```

With live BKW next-day data before midnight, expected output can be:

```text
/health -> 200 ok
/v1/status -> 200 partial_horizon
/v1/status-code -> 200 4
/v1/feedin/relative.json -> 200 {"status":"ok", "horizon_hours": <partial>, ...}
/v1/feedin/current-and-status -> 503 until +0 exists
```

From midnight, if BKW provides the full next 24 hours, status should become `ok` / `status-code 0`.

## Docker compose example

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy/examples
docker compose up -d --build
```

Docker is not installed on the Rootkeeper Pi, but the image has been built and run on Synology Docker through Portainer.

Current Portainer deployment:

```text
Stack: bkw-tariff-proxy-test
Portainer stack ID: 22
Container: bkw-tariff-proxy-test
URL from Hausnetz: http://192.168.5.40:8785
Image: bkw-tariff-proxy:local
Health: healthy
Mode: live BKW API; BKW_TEST_DATA_MODE=off
Current pre-midnight status: partial_horizon / status-code 4
```

See `docs/portainer-test-deployment.md` for the exact evidence and the volume-permission pitfall fixed during testing.

The container image runs as non-root `appuser`, exposes port `8785`, persists `/data`, and has a `/health` healthcheck.

The current local stack is already switched to live BKW mode. The production template remains useful for later renaming/public distribution:

```text
examples/portainer-production-stack.template.yml
```

Before public/product use, agree the final product/container/template name and decide whether to rename the local `*-test` stack. See:

```text
docs/go-live-and-naming-plan.md
```

## Synthetic Loxone test mode

Synthetic mode is now disabled in the Synology stack. Keep it only as an explicit lab/testing tool:

```yaml
BKW_TEST_DATA_MODE: synthetic
```

Effects:

```text
/ -> flat Loxone template JSON
/v1/loxone.json -> same flat Loxone template JSON
/v1/status -> ok
/v1/status-code -> 0
/v1/feedin/relative/0...23 -> 24 plain numeric CHF/kWh test values
```

Flat root fields for command recognitions:

```text
status_code
feedin_current
feedin_current_mchf_kwh
feedin_relative_00 ... feedin_relative_23
feedin_relative_00_mchf_kwh ... feedin_relative_23_mchf_kwh
```

For Loxone command recognitions, prefer the `*_mchf_kwh` integer fields. They are scaled as milli-CHF/kWh, so `45` means `0.045 CHF/kWh`. This avoids decimal separator parsing issues in Loxone where a JSON value such as `0.045` may be highlighted correctly but evaluated as `0`.

These values are deliberately fake and are only for validating Loxone virtual HTTP inputs, freshness, parsing, template export, and EMS gating. Production/live operation must use `BKW_TEST_DATA_MODE=off` or no variable.

The final Loxone Library/template export can now be finalized against real BKW data once the downstream Loxone optimizer behavior is confirmed.

## Endpoint shape

- `GET /health` → `ok`
- `GET /` → flat Loxone template JSON for parent virtual HTTP input command recognitions
- `GET /v1/loxone.json` → same flat Loxone template JSON as `/`
- `GET /v1/status` → `ok`, `no_data`, `stale`, `api_error`, `partial_horizon`, `unit_unknown`
- `GET /v1/status-code` → numeric status for Loxone
- `GET /v1/feedin/current` → plain numeric CHF/kWh, or 503 when unavailable
- `GET /v1/feedin/current-and-status` → `status_code;value`, e.g. `0;0.081000`
- `GET /v1/feedin/relative/{offset}` → plain numeric CHF/kWh for `+0 ... +23`, or 503 when unavailable
- `GET /v1/feedin/relative.json` → full normalized debug JSON

## Status code mapping

```text
0 = ok
1 = no_data
2 = stale
3 = api_error
4 = partial_horizon
5 = unit_unknown
99 = unknown internal state
```

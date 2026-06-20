# bkw-tariff-proxy

Docker HTTP service for BKW dynamic feed-in tariffs and Loxone virtual HTTP inputs.

## Product goal

BKW Dynamic Feed-in Tariff → local Docker HTTP service → Loxone Spotpreis-Optimierer in relative mode.

This service polls BKW once, caches the result locally, and exposes simple LAN HTTP endpoints so Loxone does not need to parse complex JSON or talk to BKW directly.

## Current status

Docker/FastAPI MVP is deployed on Synology/Portainer and currently runs in synthetic Loxone test mode.

Observed BKW state on 2026-06-20:

```text
Swagger: 200 OK
Live tariff endpoints: 404 with empty body
```

The app treats BKW 404 as `no_data`, not as a crash.

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
14 passed, 1 warning
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

With current BKW 404 state, expected output is:

```text
/health -> 200 ok
/v1/status -> 200 no_data
/v1/status-code -> 200 1
/v1/feedin/relative.json -> 200 {"status":"no_data",...}
/v1/feedin/current-and-status -> 503 {"detail":"no valid current feed-in value"}
```

## Docker compose example

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy/examples
docker compose up -d --build
```

Docker is not installed on the Rootkeeper Pi, but the image has been built and run on Synology Docker through Portainer.

Current Portainer test deployment:

```text
Stack: bkw-tariff-proxy-test
Portainer stack ID: 22
Container: bkw-tariff-proxy-test
URL from Hausnetz: http://192.168.5.40:8785
Image: bkw-tariff-proxy:local
Health: healthy
Mode: synthetic Loxone test data
Status: ok / status-code 0
```

See `docs/portainer-test-deployment.md` for the exact evidence and the volume-permission pitfall fixed during testing.

The container image runs as non-root `appuser`, exposes port `8785`, persists `/data`, and has a `/health` healthcheck.

## Synthetic Loxone test mode

While BKW live endpoints still return `404`, the Portainer test stack can run with rolling synthetic values:

```yaml
BKW_TEST_DATA_MODE: synthetic
```

Effects:

```text
/v1/status -> ok
/v1/status-code -> 0
/v1/feedin/relative/0...23 -> 24 plain numeric CHF/kWh test values
```

These values are deliberately fake and are only for validating Loxone virtual HTTP inputs, freshness, parsing, and EMS gating. Disable the variable or set it to `off` before switching to real BKW data.

## Endpoint shape

- `GET /health` → `ok`
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

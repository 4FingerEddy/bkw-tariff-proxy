# bkw-tariff-proxy

Open-source HTTP proxy for BKW dynamic feed-in tariffs and Loxone Virtual HTTP Inputs.

The service polls BKW's public dynamic feed-in tariff endpoint, stores the received Swiss local tariff day, normalizes quarter-hour `feed_in` values into absolute hourly values, and exposes Loxone-friendly HTTP endpoints.

## Use case

BKW's dynamic Swiss feed-in tariff is not one of the built-in spot-market sources in the Loxone Spot Price Optimizer. This proxy provides the missing local integration path:

```text
BKW API -> self-hosted Docker proxy -> Loxone Virtual HTTP Input -> Spot Price Optimizer
```

This is a **feed-in tariff**, not an electricity-consumption/import price.

## Features

- FastAPI service packaged as a non-root Docker container.
- Multi-architecture image for `linux/amd64` and `linux/arm64`.
- Persistent day store under `/data`, surviving upstream outages and restarts.
- `feed_in` values normalized to `CHF/kWh` and not inverted.
- Absolute local day slots `h00 ... h23` for the Spot Price Optimizer in **Absolute mode**.
- Integer `mCHF/kWh` fields for reliable Loxone parsing.
- Numeric status code for fail-closed guard logic.
- Explicit degraded-data policy for exactly one incomplete/missing hour.
- Optional synthetic test mode for safe Loxone wiring tests.

## Release target

The current source tree prepares release `v0.2.0`:

```text
ghcr.io/4fingereddy/bkw-tariff-proxy:0.2.0
```

Before using that tag, verify that release `v0.2.0` and its container image have actually been published. Production deployments should pin a version tag or immutable digest, never `latest`.

## Quick start

Docker and Compose must already be installed. Copy `examples/docker-compose.yml`, review the LAN port exposure, then run:

```bash
docker compose pull
docker compose up -d
docker compose ps
```

Smoke checks, with `PROXY_HOST` replaced by the Docker host's trusted LAN address or local DNS name:

```bash
curl -fsS http://PROXY_HOST:8785/health
curl -fsS http://PROXY_HOST:8785/v1/status-code
curl -fsS http://PROXY_HOST:8785/v1/loxone.json
```

Full deployment and rollback instructions: [`RUNBOOK.md`](RUNBOOK.md).

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

Keep port `8785` on a trusted LAN. Do not expose or forward it to the internet.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `BKW_ENDPOINT` | BKW energy-return endpoint | Upstream tariff URL |
| `POLL_INTERVAL_SECONDS` | `900` | Background polling interval |
| `UPSTREAM_WARN_AGE_SECONDS` | `7200` | Diagnostic upstream-age warning threshold |
| `DATA_DIR` | `/data` | Persistent cache directory |
| `TZ` | `Europe/Zurich` | Tariff timezone |
| `REQUIRE_COMPLETE_DAY` | `true` | Require a validated local day except the explicit one-hour tolerance |
| `BKW_TEST_DATA_MODE` | `off` | Set to `synthetic` only for lab/wiring tests |

Legacy `CACHE_MAX_AGE_SECONDS` and `REQUIRE_FULL_HORIZON` remain code-level compatibility fallbacks, but new deployments should use the current names above.

## Endpoints

- `GET /health` -> `ok`
- `GET /` -> flat Loxone JSON payload
- `GET /v1/loxone.json` -> same flat Loxone JSON payload
- `GET /v1/status` -> text status
- `GET /v1/status-code` -> numeric safety status
- `GET /v1/feedin/current` -> current local-hour value or HTTP 503
- `GET /v1/feedin/current-and-status` -> `status_code;value` or HTTP 503
- `GET /v1/feedin/relative/{offset}` -> diagnostic rolling value or HTTP 503
- `GET /v1/feedin/relative.json` -> diagnostic JSON, not a productive optimizer source

## Loxone mapping

The shared Library template is intentionally minimal:

- one parent Virtual HTTP Input on `/v1/loxone.json`;
- one `status-code` recognition;
- 24 signed analogue recognitions `h00 ... h23` using the integer fields;
- Spot Price Optimizer in **Absolute mode**.

Recognition examples:

```text
status-code -> \i"status_code":\i\v
h00         -> \i"feedin_h00_mchf_kwh":\i\v
h01         -> \i"feedin_h01_mchf_kwh":\i\v
...
h23         -> \i"feedin_h23_mchf_kwh":\i\v
```

Transport and Loxone correction:

```text
JSON transport value:       45 mCHF/kWh
Virtual Input correction:   0..1000 -> 0..1
Spot Price Optimizer value: 0.045 CHF/kWh
```

Do not feed raw integer mCHF/kWh values into the Spot Price Optimizer. The exported template applies the correction on every hour input and displays `<v.3>CHF`.

Detailed mapping: [`docs/loxone-endpoints.md`](docs/loxone-endpoints.md).

Reviewed Loxone artifacts: [`data/loxone/`](data/loxone/).

Publication preparation and export checks: [`docs/library/`](docs/library/).

## Status codes and guard policy

| Code | Meaning | Productive use |
|---:|---|---|
| `0` | Complete validated dataset for today | Allowed |
| `1` | No dataset for today | Block/neutralize |
| `2` | Wrong-day/stale guard | Block/neutralize |
| `3` | Upstream/API error | Block/neutralize |
| `4` | More than one incomplete/missing hour | Block/neutralize |
| `5` | Unknown unit | Block/neutralize |
| `10` | Exactly one hour explicitly zero-filled | Allowed with visible warning |
| `99` | Unknown internal state | Block/neutralize |

Recommended guard:

```text
status_code == 0 or status_code == 10 -> optimizer may use the values
all other codes                       -> block or neutralize optimization
```

A real tariff value of `0` is legitimate. Never use zero as a generic missing-data fallback.

## Synthetic test mode

For Loxone wiring tests without depending on live BKW data:

```yaml
BKW_TEST_DATA_MODE: "synthetic"
```

Synthetic values are fake and must not be used for production optimization. Set the variable back to `off` or remove it before live use.

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

## Safety notes

- Do not expose this service directly to the internet.
- Keep `/data` persistent.
- Do not guess unknown upstream units.
- Do not consume tariff values without the status guard.
- Do not use diagnostic relative endpoints as the productive Absolute-mode optimizer source.
- Under status code `10`, one hour is deliberately fabricated as `0`; show a warning.
- Test image updates and Loxone wiring before relying on them for automation.

## Community support

This is a free community project provided as-is under the MIT license. Best-effort support is available through [GitHub Issues](https://github.com/4FingerEddy/bkw-tariff-proxy/issues). There is no official support from BKW or Loxone for this project.

## Maintenance

Pin a released container version in production. Updates are published on a best-effort basis. If BKW changes its API or returns an unknown unit, the proxy is designed to fail visibly instead of silently feeding guessed tariff values into Loxone.

## Non-affiliation

This independent community project is not affiliated with, endorsed by, or supported by BKW Energie AG or Loxone Electronics GmbH. The names "BKW" and "Loxone" are used descriptively to identify the data source and integration target.

## License

MIT — see [`LICENSE`](LICENSE).

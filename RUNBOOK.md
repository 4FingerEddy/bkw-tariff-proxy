# RUNBOOK — bkw-tariff-proxy

## Preflight

For larger project phases, run Rootkeeper's main-model preflight first:

```bash
/home/rootkeeper/.hermes/scripts/rootkeeper_model_preflight.py
```

Proceed only if it confirms Codex/GPT-5.5 is active.

## Local development check

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy
. /home/rootkeeper/.venvs/bkw-tariff-proxy/bin/activate
pytest -q
python -m py_compile src/bkw_tariff_proxy/*.py
```

## Local app smoke test

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy
rm -rf /tmp/bkw-tariff-proxy-data
mkdir -p /tmp/bkw-tariff-proxy-data
DATA_DIR=/tmp/bkw-tariff-proxy-data \
  /home/rootkeeper/.venvs/bkw-tariff-proxy/bin/uvicorn bkw_tariff_proxy.main:app \
  --host 127.0.0.1 \
  --port 8785
```

In another shell:

```bash
curl -i http://127.0.0.1:8785/health
curl -i http://127.0.0.1:8785/v1/status
curl -i http://127.0.0.1:8785/v1/status-code
curl -i http://127.0.0.1:8785/v1/feedin/relative.json
curl -i http://127.0.0.1:8785/v1/feedin/current-and-status
```

## Synthetic Loxone test mode

For full Loxone wiring tests while BKW returns `404`, enable synthetic rolling data in the stack environment:

```yaml
BKW_TEST_DATA_MODE: synthetic
```

Expected endpoints:

```text
/ -> flat Loxone template JSON with status_code, feedin_current, feedin_current_mchf_kwh, feedin_relative_00...23 and feedin_relative_00_mchf_kwh...feedin_relative_23_mchf_kwh
/v1/loxone.json -> same flat Loxone template JSON
/v1/status -> ok
/v1/status-code -> 0
/v1/feedin/relative/0 -> plain numeric test value, e.g. 0.045000
/v1/feedin/current-and-status -> 0;0.045000
/v1/feedin/relative.json -> status ok, horizon_hours 24
```

For a Loxone Library/template export, use one parent virtual HTTP input `BKW Dyntariffs` on the root URL and add nested command recognitions, e.g.:

```text
status-code -> \i"status_code":\i\v
+0          -> \i"feedin_relative_00_mchf_kwh":\i\v
+1          -> \i"feedin_relative_01_mchf_kwh":\i\v
```

Use the `*_mchf_kwh` integer fields for Loxone values. `45` means `0.045 CHF/kWh`; apply correction/factor `0.001` only if a display value in CHF/kWh is required. For optimizer ordering, the integer scale can be used directly.

Important: these are fake values. Use them only to test Loxone HTTP inputs and EMS/status gating. Before production/live BKW operation, remove the variable or set:

```yaml
BKW_TEST_DATA_MODE: off
```

## Docker / Portainer target

Docker is not installed on the Rootkeeper Pi. Use Portainer on Synology:

```text
Portainer: https://192.168.5.40:9443
Endpoint: local / id=2
Stack: bkw-tariff-proxy-test
Container: bkw-tariff-proxy-test
URL: http://192.168.5.40:8785
```

The current test stack file is:

```text
examples/portainer-test-stack.yml
```

Prepared but intentionally not deployed production template:

```text
examples/portainer-production-stack.template.yml
```

Go-live and naming checklist:

```text
docs/go-live-and-naming-plan.md
```

The historic Synology stack currently runs a locally built image until the GHCR release cutover is complete:

```text
bkw-tariff-proxy:local
```

The target published image shape is:

```text
ghcr.io/4fingereddy/bkw-tariff-proxy:<version>
```

For a manual Docker-capable host, the generic compose example remains:

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy/examples
docker compose up -d --build
```

See full deployment notes:

```text
docs/portainer-test-deployment.md
```

## BKW live API observation

See:

```text
docs/bkw-api-observations.md
```

Current live state: BKW energy-return endpoint returns HTTP 200 with 96 quarter-hour feed-in intervals. The service computes hourly arithmetic means for Loxone relative slots and reports `partial_horizon` before the current rolling 24-hour horizon is complete or when a live BKW hour has fewer than four quarter-hour intervals.

The old BKW MQTT bridge is retired. Production integration is Docker HTTP proxy -> Loxone Virtual HTTP Input.

## Safety notes

- Do not expose this service directly to the internet.
- Do not guess BKW units. Unknown unit must fail as `unit_unknown` or raise a controlled error.
- Do not feed `0` into Loxone as a silent fallback for missing data.
- Loxone should read status/horizon state and block optimization on invalid data.
- `/data` should be persistent so cache survives container restarts.

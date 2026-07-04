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
curl -i http://127.0.0.1:8785/v1/loxone.json
curl -i http://127.0.0.1:8785/v1/feedin/relative.json
curl -i http://127.0.0.1:8785/v1/feedin/current-and-status
```

## Current architecture

Production path:

```text
BKW API -> Docker HTTP proxy -> Loxone Virtual HTTP Input -> Spotpreis-Optimierer
```

The proxy is day-based, not relative-horizon-based:

- BKW publishes a Swiss local tariff day with 96 quarter-hour values on normal days.
- The proxy stores datasets by `tariff_date` in `Europe/Zurich`.
- `/v1/loxone.json` exposes absolute day slots `feedin_h00...feedin_h23` and `*_mchf_kwh` integer variants.
- Loxone Spotpreis-Optimierer must run in **Absolut** mode, not Relativ mode.
- `/v1/feedin/relative.json` and `/v1/feedin/relative/{offset}` are diagnostic rolling views only.

## Synthetic Loxone test mode

For full Loxone wiring tests without live BKW dependency, enable synthetic day data in the stack environment:

```yaml
BKW_TEST_DATA_MODE: synthetic
```

Expected endpoints:

```text
/ -> flat Loxone template JSON with status_code, tariff_date, feedin_current, feedin_current_mchf_kwh, feedin_h00...h23 and feedin_h00_mchf_kwh...feedin_h23_mchf_kwh
/v1/loxone.json -> same flat Loxone template JSON
/v1/status -> ok
/v1/status-code -> 0
/v1/feedin/current-and-status -> 0;0.045000 style value for the current local hour
/v1/feedin/relative.json -> diagnostic only, status ok while today is complete
```

For a Loxone Library/template export, use one parent virtual HTTP input `BKW Dyntariffs` on `/v1/loxone.json` and add nested command recognitions, e.g.:

```text
status-code -> \i"status_code":\i\v
h00         -> \i"feedin_h00_mchf_kwh":\i\v
h01         -> \i"feedin_h01_mchf_kwh":\i\v
...
h23         -> \i"feedin_h23_mchf_kwh":\i\v
current     -> \i"feedin_current_mchf_kwh":\i\v
```

Use the `*_mchf_kwh` integer fields for Loxone values. `45` means `0.045 CHF/kWh`; apply correction/factor `0.001` if a display value in CHF/kWh is required.

Important: synthetic values are fake. Use them only to test Loxone HTTP inputs and EMS/status gating. Before live BKW operation, remove the variable or set:

```yaml
BKW_TEST_DATA_MODE: off
```

## Docker / Portainer target

Docker is not installed on the Rootkeeper Pi. Use Portainer on Synology:

```text
Portainer: https://192.168.5.40:9443
Endpoint: local / id=2
Stack id: 22
URL: http://192.168.5.40:8785
Image: bkw-tariff-proxy:local
```

Deploy/update through the project script:

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy
. /home/rootkeeper/.venvs/bkw-tariff-proxy/bin/activate
python scripts/live_cutover_portainer.py
```

The script rebuilds the local image, updates the Portainer stack, and writes before/after audit artifacts under:

```text
/mnt/synology-rootkeeper/reports/bkw-tariff-proxy/live-cutover/
```

The target published image shape remains:

```text
ghcr.io/4fingereddy/bkw-tariff-proxy:<version>
```

## BKW live API observation

See:

```text
docs/bkw-api-observations.md
```

Current live behavior: BKW energy-return endpoint returns HTTP 200 with 96 quarter-hour feed-in intervals for one Swiss local tariff day. During the afternoon it may already publish tomorrow's day. If the proxy has no stored dataset for today at that moment, `/v1/status` correctly reports `no_data` until the next local midnight activates the stored tomorrow dataset. This is safe and acceptable for this preparation project.

The old BKW MQTT bridge is retired. Do not reactivate it.

## Loxone checklist

After deploying the proxy day-vector version:

1. Configure `BKW Dyntariffs` command recognitions to `feedin_h00_mchf_kwh` ... `feedin_h23_mchf_kwh`.
2. Configure `BKW Aktuell chf/kWh` to `feedin_current_mchf_kwh`.
3. Switch `Dynamische Einspeisevergütung` to **Absolut** mode.
4. Keep the status-code guard: `status_code == 0` unlocks, non-zero locks/neutralizes.
5. Remove or clearly control the previous override/Überbrückung path. Do not mask `api_error`, `unit_unknown`, or `no_data` as valid optimization data.

## Safety notes

- Do not expose this service directly to the internet.
- Do not guess BKW units. Unknown unit must fail as `unit_unknown` or raise a controlled error.
- Do not feed `0` into Loxone as a silent fallback for missing data.
- Loxone should read status state and block optimization on invalid data.
- `/data` must be persistent so today's cached day survives container restarts.

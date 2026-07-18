# Go-live and naming plan

This document captures the deliberate pause before creating the final Loxone template or production stack name.

## Current decision

Patrick will build/export the Loxone template later, after:

1. the BKW API returns real live tariff data;
2. the product/container/template name is agreed;
3. the HTTP payload has been verified against real tariff units and intervals.

Until then, the Synology stack remains a test stack:

```text
Stack: bkw-tariff-proxy-test
Mode:  BKW_TEST_DATA_MODE=synthetic
URL:   http://192.168.5.40:8785
```

## Naming candidates

Do not rename automatically. Decide before production and Loxone Library export.

Candidate names:

```text
bkw-tariff-proxy
bkw-loxone-tariff-proxy
bkw-dyntariff-http
bkw-feed-in-proxy
```

Recommended current working name:

```text
bkw-tariff-proxy
```

Reason: short, product-like, not Loxone-only, still specific enough.

## Current monitoring

The existing script-only Zeitauftrag still checks the BKW live API every 15 minutes:

```text
name: bkw-dyntariffs-mqtt-bridge
schedule: every 15m
script: bkw_dyntariffs_mqtt_quiet.sh
```

Even though the product direction is HTTP, this job is still useful as the API go-live sentinel. It stays silent while BKW returns `404/no_data` and emits a one-time Telegram alert when the API changes to valid tariff data.

Do not add a second BKW live watchdog unless this MQTT bridge is paused or retired, otherwise Patrick may receive duplicate go-live alerts. Docker macht wieder Docker-Dinge, aber doppelte Watchdogs machen einfach nur doppelte Geräusche.

## Go-live checklist

When BKW API becomes live:

1. Read the alert and inspect raw returned payload.
2. Verify `feed_in[].unit` before changing production behavior.
3. Run local tests:

```bash
cd /mnt/synology-rootkeeper/projects/bkw-tariff-proxy
. /home/rootkeeper/.venvs/bkw-tariff-proxy/bin/activate
pytest -q
python -m py_compile src/bkw_tariff_proxy/*.py
```

4. Temporarily test HTTP service with `BKW_TEST_DATA_MODE=off` in a controlled stack or local run.
5. Verify endpoints:

```text
/health -> ok
/v1/status-code -> 0
/v1/loxone.json -> status_code 0, horizon_hours 24, *_mchf_kwh values present
/v1/feedin/relative/0 -> real CHF/kWh decimal
```

6. Confirm Loxone status gating:

```text
status_code == 0  -> optimizer allowed with complete values
status_code == 10 -> optimizer allowed with one explicit zero-filled hour; warning/status display required
all other codes  -> optimizer blocked / normal mode
```

7. Agree final name.
8. Create production Portainer stack from `examples/portainer-production-stack.template.yml`.
9. Keep the synthetic test stack until production has run cleanly.
10. Export Loxone Library/template only after the final name is fixed.

## Production stack template

The file:

```text
examples/portainer-production-stack.template.yml
```

is intentionally not deployed yet.

Key differences from test stack:

```text
container_name: bkw-tariff-proxy
ports: 192.168.5.40:8785:8785
BKW_TEST_DATA_MODE: off
volume: bkw-tariff-proxy-data
```

## Do not do yet

- Do not rename the running stack while it is still a synthetic Loxone test endpoint.
- Do not export the Loxone Library/template before final naming.
- Do not expose the service via NAS reverse proxy unless a real external-access requirement exists.
- Do not remove decimal CHF/kWh fields; keep them for debugging and non-Loxone clients.
- Do not switch from synthetic to live until BKW API returns real data and units have been checked.

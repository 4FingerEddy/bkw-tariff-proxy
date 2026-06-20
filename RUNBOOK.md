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

The image was built through Portainer's Docker API proxy and is currently tagged on Synology as:

```text
bkw-tariff-proxy:local
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

Current live state: BKW Swagger is reachable; tariff endpoints return 404 with empty body. The service maps that to `no_data` and keeps Loxone endpoints available.

## Safety notes

- Do not expose this service directly to the internet.
- Do not guess BKW units. Unknown unit must fail as `unit_unknown` or raise a controlled error.
- Do not feed `0` into Loxone as a silent fallback for missing data.
- Loxone should read status/horizon state and block optimization on invalid data.
- `/data` should be persistent so cache survives container restarts.

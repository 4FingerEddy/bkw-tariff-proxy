# Public runbook — bkw-tariff-proxy

This runbook starts at the point where Docker Engine with Compose, or Portainer, is already available.

## 1. Prerequisites

- Docker host with a stable LAN IP address or local DNS name.
- Loxone Miniserver can reach TCP port `8785` on that host.
- Container has outbound HTTPS access to `api.bkw.ch`.
- Port `8785` is not exposed or forwarded to the internet.
- Loxone Config with the Spot Price Optimizer function block.

## 2. Deploy a pinned release

Copy `examples/docker-compose.yml` and verify the image tag before starting:

```yaml
image: ghcr.io/4fingereddy/bkw-tariff-proxy:0.2.0
```

Do not use `latest` for production. The named `/data` volume must remain persistent.

```bash
docker compose pull
docker compose up -d
docker compose ps
```

The container should report `healthy`.

## 3. Verify the service

Replace `PROXY_HOST` with the Docker host's trusted LAN address or local DNS name:

```bash
curl -fsS http://PROXY_HOST:8785/health
curl -fsS http://PROXY_HOST:8785/v1/status-code
curl -fsS http://PROXY_HOST:8785/v1/loxone.json
```

Expected basics:

- `/health` returns `ok`.
- `/v1/status-code` returns a numeric status.
- `/v1/loxone.json` returns a flat JSON object with `status_code` and `feedin_h00_mchf_kwh` through `feedin_h23_mchf_kwh`.
- Immediately after first start, status code `1` can be normal until the first usable BKW tariff day is available.

## 4. Optional synthetic wiring test

Synthetic mode is for lab and Loxone wiring tests only:

```yaml
BKW_TEST_DATA_MODE: "synthetic"
```

Recreate the container and verify status code `0` plus 24 populated hourly values:

```bash
docker compose up -d --force-recreate
```

Before live use, set the variable back to `off` or remove it, recreate the container, and repeat the endpoint checks.

## 5. Connect Loxone

Follow:

- `docs/loxone-endpoints.md`
- `docs/library/export-checklist.md`

The production mapping uses:

- one Virtual HTTP Input on `http://PROXY_HOST:8785/v1/loxone.json`;
- `status_code` plus the 24 absolute fields `feedin_h00_mchf_kwh` through `feedin_h23_mchf_kwh`;
- Spot Price Optimizer in **Absolute mode**;
- optimization enabled only for status codes `0` and `10`.

## 6. Status codes

| Code | Meaning | Loxone action |
|---:|---|---|
| `0` | Complete validated tariff day | Optimization may run |
| `1` | No usable tariff day | Block or neutralize |
| `2` | Wrong-day/stale guard | Block or neutralize |
| `3` | Upstream/API error | Block or neutralize |
| `4` | More than one incomplete/missing hour | Block or neutralize |
| `5` | Unknown unit | Block or neutralize |
| `10` | Exactly one hour explicitly zero-filled | May run; show degraded-data warning |
| `99` | Unknown internal state | Block or neutralize |

A real tariff value of `0` is valid. Do not interpret zero as missing data.

## 7. Update and rollback

Before updating, note the currently pinned tag and keep the persistent volume:

```bash
docker compose pull
docker compose up -d
```

Then repeat all endpoint checks. To roll back, restore the previous image tag and run the same commands. Do not delete the `/data` volume during a normal rollback.

## 8. Troubleshooting

- Container unhealthy: inspect `docker compose logs bkw-tariff-proxy`.
- Miniserver cannot connect: verify LAN routing, firewall, host/port and that no reverse proxy is required.
- Status `1`: wait for a usable BKW tariff day and inspect `/v1/loxone.json`.
- Status `3`: verify outbound HTTPS and inspect container logs.
- Status `4`: upstream data is incomplete beyond the tolerated one-hour policy.
- Status `5`: do not override the guard; report the unexpected unit.
- Loxone parses decimals as zero: use only the integer `*_mchf_kwh` fields.
- Synthetic values remain active: set `BKW_TEST_DATA_MODE` back to `off` and recreate the container.

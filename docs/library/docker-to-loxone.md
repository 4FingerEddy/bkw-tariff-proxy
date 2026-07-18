# Docker-to-Loxone setup

This guide starts with an existing Docker Engine/Compose or Portainer environment.

## 1. Prepare the Docker host

The host needs:

- a stable trusted-LAN IP address or local DNS name;
- inbound TCP `8785` from the Loxone Miniserver;
- outbound HTTPS to `api.bkw.ch`;
- no internet port-forward for `8785`.

## 2. Deploy the proxy

Copy `examples/docker-compose.yml` and verify that the selected image tag has been published:

```bash
docker compose pull
docker compose up -d
docker compose ps
```

Keep the named `/data` volume. The container should become healthy.

## 3. Verify endpoints

Replace `PROXY_HOST` with the host's LAN address or local DNS name:

```bash
curl -fsS http://PROXY_HOST:8785/health
curl -fsS http://PROXY_HOST:8785/v1/status-code
curl -fsS http://PROXY_HOST:8785/v1/loxone.json
```

Verify:

- health is `ok`;
- status is numeric;
- the flat JSON contains `status_code`;
- fields `feedin_h00_mchf_kwh` through `feedin_h23_mchf_kwh` exist;
- productive values are populated only for status `0` or `10`.

## 4. Optional synthetic test

Set:

```yaml
BKW_TEST_DATA_MODE: "synthetic"
```

Recreate the container:

```bash
docker compose up -d --force-recreate
```

Verify status `0` and 24 fake hourly values. Synthetic values are for wiring tests only.

## 5. Build and export the Loxone template

Follow `export-checklist.md`. The final XML must come from a real Loxone Config export from a fresh project and use:

```text
http://REPLACE_WITH_PROXY_HOST:8785/v1/loxone.json
```

The template contains one status input and 24 absolute hourly inputs.

## 6. Wire the Spot Price Optimizer

- Select **Absolute mode**.
- Connect `h00` to `00:00`, through `h23` to `23:00`.
- Keep the template correction `0..1000 -> 0..1` on every signed hour input.
- Confirm that transport value `45` reaches the optimizer as `0.045 CHF/kWh`.
- Permit productive optimization only when status is `0` or `10`.
- Show a degraded-data warning for status `10`.
- Block or neutralize every other status.

## 7. Test the safety guard

With synthetic mode active:

1. Confirm 24 values and status `0`.
2. Confirm the optimizer can calculate while the guard is open.
3. Stop the proxy or make it unreachable.
4. Confirm productive automation does not continue on unavailable/unsafe data.
5. Restart the proxy and confirm recovery.

## 8. Switch to live data

Set:

```yaml
BKW_TEST_DATA_MODE: "off"
```

or remove the variable, then recreate the container. Repeat all endpoint and status-guard checks before relying on the integration.

## 9. Update and rollback

Update by changing only the pinned image tag, pulling and recreating. Keep the previous tag and persistent volume for rollback. Repeat endpoint and Loxone safety checks after every change.

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| Container is unhealthy | `docker compose logs bkw-tariff-proxy` |
| Miniserver cannot connect | LAN route, firewall, host and port |
| Status `1` | Wait for a usable BKW tariff day |
| Status `3` | Outbound HTTPS and container logs |
| Status `4` | Upstream day is incomplete beyond tolerance |
| Status `5` | Do not override; report the unknown unit |
| Status `10` | Keep visible degraded-data warning |
| Loxone shows decimal values as zero | Use integer `*_mchf_kwh` fields |
| Values remain synthetic | Set test mode to `off` and recreate |

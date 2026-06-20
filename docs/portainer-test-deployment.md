# Portainer test deployment

Observed and deployed on 2026-06-20 via Portainer API.

## Portainer / Docker target

```text
Portainer: https://192.168.5.40:9443
Portainer version: 2.39.3
Endpoint: local / id=2 / unix:///var/run/docker.sock
Docker: 24.0.2 linux/amd64
```

## Stack

```text
Name: bkw-tariff-proxy-test
Stack ID: 22
Compose file in project: examples/portainer-test-stack.yml
Container: bkw-tariff-proxy-test
Published port: 192.168.5.40:8785 -> container :8785
Image: bkw-tariff-proxy:local
Image ID: sha256:4a9bcdb05be1...
User inside container: appuser
Restart policy: unless-stopped
Health: healthy
Volume: bkw-tariff-proxy-test_bkw-tariff-proxy-data-v2 -> /data
```

## Build method used

Because the Rootkeeper Pi itself has no Docker CLI, the Docker image was built through the Portainer proxy to the Docker API:

```text
POST /api/endpoints/2/docker/build?t=bkw-tariff-proxy:local&dockerfile=Dockerfile&rm=1
Content-Type: application/x-tar
```

The tar build context was created from the NAS project path and excluded `.git`, caches, pycache, venvs, and egg-info.

## Runtime verification from Pi

```text
GET http://192.168.5.40:8785/health -> 200 ok
GET http://192.168.5.40:8785/v1/status -> 200 no_data
GET http://192.168.5.40:8785/v1/status-code -> 200 1
GET http://192.168.5.40:8785/v1/feedin/relative.json -> 200 {"status":"no_data",...}
GET http://192.168.5.40:8785/v1/feedin/current-and-status -> 503 {"detail":"no valid current feed-in value"}
GET http://192.168.5.40:8785/v1/feedin/relative/0 -> 503 {"detail":"no valid feed-in value for offset 0"}
```

This is expected while BKW returns 404/no tariff data.

## Pitfall fixed

The first temporary Portainer stack used `python:3.12-slim` and installed dependencies at runtime as root. It created the initial named volume with root-owned cache data. After switching to the real built image running as non-root `appuser`, the app could not write `/data/cache.json`.

Fix used:

1. Build the real Dockerfile image `bkw-tariff-proxy:local`.
2. Update the stack to use a fresh named volume `bkw-tariff-proxy-data-v2`.
3. Remove the old unused volume `bkw-tariff-proxy-test_bkw-tariff-proxy-data`.

Future production deployment should avoid the temporary runtime-pip stack and use the actual built image or a registry image from the start.

# LOXONE Library entry draft

## Classification

- **Title:** BKW Dynamic Feed-in Tariff Switzerland
- **Type:** Community Network Template
- **Creator:** 4FingerEddy
- **Brand:** BKW (descriptive data-source reference)
- **Version:** match the released proxy/template version

## Teaser

Reads BKW's dynamic Swiss feed-in tariff through a small self-hosted Docker proxy and provides 24 absolute hourly values plus a numeric safety status for the Loxone Spot Price Optimizer.

## Overview

This community template integrates BKW's dynamic Swiss feed-in tariff into Loxone. BKW publishes quarter-hour feed-in values for a Swiss local tariff day. A small open-source Docker proxy fetches and validates the upstream data, groups it into 24 absolute hourly values in `Europe/Zurich`, and exposes a flat JSON document for a Loxone Virtual HTTP Input.

```text
BKW API -> self-hosted Docker proxy -> Loxone Virtual HTTP Input -> Spot Price Optimizer
```

Use the Spot Price Optimizer in **Absolute mode**. The template supplies the hours `00:00` through `23:00` as signed integer milli-CHF/kWh values. Example: `45` means `0.045 CHF/kWh`. Apply factor `0.001` only when displaying CHF/kWh.

The numeric status input is the automation safety boundary:

```text
status_code == 0  -> complete validated tariff day; optimization may run
status_code == 10 -> exactly one hour was explicitly zero-filled; optimization may run with a visible warning
all other codes   -> block or neutralize optimization
```

A real tariff value of zero is valid and is not automatically missing. This is a feed-in tariff, not an electricity-consumption/import price.

Source, container deployment, endpoint documentation and troubleshooting:

https://github.com/4FingerEddy/bkw-tariff-proxy

## Prerequisites

- Existing Docker Engine with Compose, or Portainer.
- A stable LAN address or local DNS name for the Docker host.
- Network access from the Loxone Miniserver to TCP port `8785` on that host.
- Outbound HTTPS from the container to `api.bkw.ch`.
- Loxone Config and a Miniserver with the Spot Price Optimizer function block.
- An applicable BKW dynamic Swiss feed-in tariff arrangement.

Do not expose the proxy port to the internet.

## Installation summary

1. Deploy the pinned container release with the repository's `examples/docker-compose.yml`.
2. Keep the `/data` volume persistent.
3. Verify `/health`, `/v1/status-code` and `/v1/loxone.json`.
4. Optionally use `BKW_TEST_DATA_MODE=synthetic` for wiring tests.
5. Import the XML as a Virtual HTTP Input and replace `REPLACE_WITH_PROXY_HOST` with the Docker host's LAN address or local DNS name.
6. Connect the 24 values to the Spot Price Optimizer in Absolute mode.
7. Add the status guard before enabling productive automation.
8. Return synthetic mode to `off` before live use.

## Productive command recognitions

The final exported template contains exactly these 25 signed analogue recognitions:

| Input | Command recognition |
|---|---|
| `status-code` | `\i"status_code":\i\v` |
| `h00` | `\i"feedin_h00_mchf_kwh":\i\v` |
| `h01` | `\i"feedin_h01_mchf_kwh":\i\v` |
| `h02` | `\i"feedin_h02_mchf_kwh":\i\v` |
| `h03` | `\i"feedin_h03_mchf_kwh":\i\v` |
| `h04` | `\i"feedin_h04_mchf_kwh":\i\v` |
| `h05` | `\i"feedin_h05_mchf_kwh":\i\v` |
| `h06` | `\i"feedin_h06_mchf_kwh":\i\v` |
| `h07` | `\i"feedin_h07_mchf_kwh":\i\v` |
| `h08` | `\i"feedin_h08_mchf_kwh":\i\v` |
| `h09` | `\i"feedin_h09_mchf_kwh":\i\v` |
| `h10` | `\i"feedin_h10_mchf_kwh":\i\v` |
| `h11` | `\i"feedin_h11_mchf_kwh":\i\v` |
| `h12` | `\i"feedin_h12_mchf_kwh":\i\v` |
| `h13` | `\i"feedin_h13_mchf_kwh":\i\v` |
| `h14` | `\i"feedin_h14_mchf_kwh":\i\v` |
| `h15` | `\i"feedin_h15_mchf_kwh":\i\v` |
| `h16` | `\i"feedin_h16_mchf_kwh":\i\v` |
| `h17` | `\i"feedin_h17_mchf_kwh":\i\v` |
| `h18` | `\i"feedin_h18_mchf_kwh":\i\v` |
| `h19` | `\i"feedin_h19_mchf_kwh":\i\v` |
| `h20` | `\i"feedin_h20_mchf_kwh":\i\v` |
| `h21` | `\i"feedin_h21_mchf_kwh":\i\v` |
| `h22` | `\i"feedin_h22_mchf_kwh":\i\v` |
| `h23` | `\i"feedin_h23_mchf_kwh":\i\v` |

## Data-quality warning

External tariff data can be unavailable, incomplete or changed upstream. Keep the status guard in place. For any status other than `0` or `10`, block or neutralize optimization. Under status `10`, one hour is a deliberately fabricated zero and must be shown as degraded data. Never bypass an unknown-unit status.

## Support

This is a free community template provided as-is under the MIT license. Best-effort support is available through GitHub Issues:

https://github.com/4FingerEddy/bkw-tariff-proxy/issues

There is no official support from BKW or Loxone for this template.

## Maintenance

Pin a released container version for production. Test updates with synthetic mode before live use. API compatibility and project updates are maintained on a best-effort basis.

## Non-affiliation

Independent community project. Not affiliated with, endorsed by, or supported by BKW Energie AG or Loxone Electronics GmbH. The names "BKW" and "Loxone" are used descriptively to identify the data source and integration target.

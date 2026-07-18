# BKW API observations

This document records public API behavior relevant to the proxy. It is not a live service-status page.

## Swagger

```text
URL: https://api.bkw.ch/api/dyntariffs/swagger/v1/swagger.json
HTTP observed: 200
Content-Type observed: application/json;charset=utf-8
Title: BKW Dynamic Tariffs API
Version: v1
Paths:
- /api/dyntariffs/v1/Tariffs
- /api/dyntariffs/v1/Tariffs/energyreturn
```

## Schema summary

`TariffDto` contains:

- `publication_timestamp`
- `prices[]`

Each price entry contains interval timestamps and component arrays such as:

- `electricity`
- `feed_in`
- `grid`
- `integrated`
- `regional_fees`

Each price component has a declared `unit` and `value`. This project reads the feed-in component and accepts only a known CHF/kWh unit mapping.

## Historical endpoint status — 2026-06-20

The tariff endpoints initially returned HTTP 404 with an empty body. The proxy treated that as unavailable data and kept its local status endpoints available so Loxone could fail closed.

## Live endpoint observation — 2026-07-02

The energy-return endpoint returned:

```text
HTTP: 200
publication_timestamp: 2026-07-02T15:45:00Z
interval_count: 96
cadence: quarter-hour
unit: CHF_kWh
first_start_local: 2026-07-03T00:00:00+02:00
last_end_local: 2026-07-04T00:00:00+02:00
```

## Current data model

- The proxy is based on a Swiss local tariff day, not a rolling production horizon.
- Quarter-hour feed-in values are grouped into absolute local hours using the arithmetic mean.
- `/v1/loxone.json` exposes absolute `h00` through `h23` fields for the Spot Price Optimizer in Absolute mode.
- A valid today vector remains usable until local midnight; upstream age remains diagnostic.
- Exactly one incomplete/missing local hour may be explicitly zero-filled and reported as status code `10`.
- More than one incomplete/missing hour fails closed as status code `4`.
- Duplicate interval starts and inconsistent cached metadata fail closed.
- The proxy keeps unavailable-data and unknown-unit handling even when the upstream endpoint is currently healthy.

The upstream API may change. Consumers must use the proxy status code rather than assuming every HTTP 200 payload is suitable for automation.

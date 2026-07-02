# BKW API observations

Observed from Rootkeeper.

## Swagger

```text
URL: https://api.bkw.ch/api/dyntariffs/swagger/v1/swagger.json
HTTP: 200
Content-Type: application/json;charset=utf-8
Title: BKW Dynamic Tariffs API
Version: v1
Paths:
- /api/dyntariffs/v1/Tariffs
- /api/dyntariffs/v1/Tariffs/energyreturn
```

## Schema summary

`TariffDto`:

- `publication_timestamp`
- `prices[]`

Each `PriceDto` contains interval timestamps and component arrays such as:

- `electricity`
- `feed_in`
- `grid`
- `integrated`
- `regional_fees`

Each price component has:

- `unit`
- `value`

For this product, use `feed_in[0].value` and normalize the declared `unit` to `CHF/kWh`.

## Historical endpoint status — 2026-06-20

Observed endpoints returned naked 404 with zero-byte body:

```text
https://api.bkw.ch/api/dyntariffs/v1/Tariffs/energyreturn -> 404 bytes=0
https://api.bkw.ch/api/dyntariffs/v1/Tariffs -> 404 bytes=0
https://api.bkw.ch/api/dyntariffs/v1/tariffs/energyreturn -> 404 bytes=0
https://api.bkw.ch/api/dyntariffs/v1/tariffs/ -> 404 bytes=0
```

Interpretation at the time: treat 404 as `no_data`, not as application crash. Keep serving local status endpoints so Loxone can block optimization cleanly until BKW data appears.

## Live endpoint status — 2026-07-02

`GET /api/dyntariffs/v1/Tariffs/energyreturn` is live:

```text
HTTP: 200
publication_timestamp: 2026-07-02T15:45:00Z
interval_count: 96
cadence: quarter-hour
unit: CHF_kWh
first_start_local: 2026-07-03T00:00:00+02:00
last_end_local: 2026-07-04T00:00:00+02:00
```

Operational interpretation:

- BKW publishes next-day feed-in data, currently 96 quarter-hour intervals.
- The HTTP proxy groups quarter-hour values into hourly Loxone relative slots using the arithmetic mean of the available quarter-hour values inside each hour.
- Before midnight, `+0` may be unavailable because the feed begins at next local midnight. The proxy reports `partial_horizon` / status-code `4` instead of inventing fallback values.
- From midnight, if a full 24-hour rolling horizon is available, status should become `ok` / status-code `0`.
- Keep 404/no_data handling for resilience; do not remove it just because the API is currently live.

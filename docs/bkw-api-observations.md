# BKW API observations

Observed from Rootkeeper on 2026-06-20.

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

## Live endpoint status

Observed endpoints all returned naked 404 with zero-byte body:

```text
https://api.bkw.ch/api/dyntariffs/v1/Tariffs/energyreturn -> 404 bytes=0
https://api.bkw.ch/api/dyntariffs/v1/Tariffs -> 404 bytes=0
https://api.bkw.ch/api/dyntariffs/v1/tariffs/energyreturn -> 404 bytes=0
https://api.bkw.ch/api/dyntariffs/v1/tariffs/ -> 404 bytes=0
```

Interpretation: treat 404 as `no_data`, not as application crash. Keep serving local status endpoints so Loxone can block optimization cleanly until BKW data appears.

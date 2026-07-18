# Loxone endpoint mapping

## Base URL

Use a stable LAN address or local DNS name for the Docker host:

```text
http://PROXY_HOST:8785/v1/loxone.json
```

Do not put a private production address, token or internet-facing URL into a shared template.

## Productive mapping

The integration is day-based:

- BKW publishes one Swiss local tariff day.
- The proxy stores values by `tariff_date` in `Europe/Zurich`.
- `/v1/loxone.json` exposes 24 absolute day slots.
- The Spot Price Optimizer must run in **Absolute mode**.
- Relative endpoints are diagnostic only and are not part of the Library template.

Create one parent Virtual HTTP Input:

```text
Name: BKW Dynamic Feed-in Tariff CH
URL:  http://PROXY_HOST:8785/v1/loxone.json
Polling cycle: 900 s
```

The 900-second polling cycle is a practical match for the proxy's default upstream polling interval. It is not a substitute for the status guard.

## Library-template command recognitions

Use exactly 25 productive recognitions: one status input and 24 absolute hour inputs.

```text
status-code -> \i"status_code":\i\v
h00         -> \i"feedin_h00_mchf_kwh":\i\v
h01         -> \i"feedin_h01_mchf_kwh":\i\v
...
h23         -> \i"feedin_h23_mchf_kwh":\i\v
```

All tariff inputs are signed analogue values. Negative feed-in tariffs are possible.

The JSON transport scale is integer milli-CHF/kWh. Correct every productive hour input in Loxone before connecting it to the optimizer:

```text
JSON transport value:       45 mCHF/kWh
Virtual Input correction:   0..1000 -> 0..1
Spot Price Optimizer value: 0.045 CHF/kWh
Display unit:               <v.3>CHF
```

Enable signed interpretation on every hour input because negative tariffs are valid. Do not feed the raw integer transport values directly into the Spot Price Optimizer.

## Status guard

```text
status_code == 0  -> complete data; optimizer may run
status_code == 10 -> one explicitly zero-filled hour; optimizer may run with a visible warning
all other codes   -> block or neutralize optimization
```

A tariff value of `0` is legitimate. Missing or unsafe tariff fields are represented as JSON `null` outside the explicitly tolerated status `10` case.

## Fields deliberately excluded from the Library template

The public template does not recognize:

- decimal tariff fields, because Loxone decimal parsing can be locale-sensitive;
- the current-value field, because the productive optimizer uses the 24 absolute hours;
- diagnostic string/list fields;
- upstream-age metadata;
- relative diagnostic views.

Operators can still inspect the full JSON and diagnostic endpoints with a browser or `curl`.

## Import and verification

The final XML must be produced by a real Loxone Config export from a fresh, anonymous project. See `docs/library/export-checklist.md`. After export, re-import the XML into another fresh project and verify all 25 recognitions before any Library submission.

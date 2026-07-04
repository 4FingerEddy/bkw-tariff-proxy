# Loxone endpoint mapping

Base URL example:

```text
http://192.168.5.40:8785/v1/loxone.json
```

Current Synology stack mode:

```text
live BKW API data
BKW_TEST_DATA_MODE=off
```

## Target behavior

The BKW integration is day-based:

- BKW publishes one Swiss local tariff day.
- The proxy stores values by local `tariff_date` in `Europe/Zurich`.
- `/v1/loxone.json` exposes 24 absolute day slots `feedin_h00...feedin_h23`.
- The Loxone Spotpreis-Optimierer `Dynamische Einspeisevergütung` must be configured in **Absolut** mode.
- Relative endpoints are diagnostic only and must not be used as the productive optimizer input.

## Diagnostic relative endpoint

For troubleshooting, use `/v1/feedin/relative.json` as the tracking endpoint. It separates productive status from diagnostic values:

```text
status / status_code              -> effective safety status used by Loxone
day_today_status                  -> ok / no_data / partial_horizon / stale for today's local day
day_tomorrow_status               -> ok / pending / partial_horizon for tomorrow
upstream_status                   -> ok / error for latest upstream contact
safe_values_available             -> true only when plain value endpoints may be used
diagnostic_only                   -> true
relative[]                        -> rolling diagnostic slots; not the Spotpreis-Optimierer source
```

## Recommended Loxone template structure

Use one parent virtual HTTP input:

```text
Name: BKW Dyntariffs
URL:  http://192.168.5.40:8785/v1/loxone.json
```

Under this parent, create the command recognitions as nested virtual inputs. The root JSON is intentionally flat, so each input can use one unique key.

Prefer the integer `*_mchf_kwh` fields for tariff values. Loxone may highlight JSON decimal values like `0.045` correctly but still evaluate `\v` as `0` because of decimal separator parsing. The integer fields avoid this.

Scale:

```text
mchf_kwh = milli-CHF/kWh
45       = 0.045 CHF/kWh
52       = 0.052 CHF/kWh
```

For display in CHF/kWh, apply a correction/factor of `0.001` in Loxone. For optimizer ordering, the integer scale can be used directly if all values use the same scale.

BKW live data is quarter-hourly. The proxy groups quarter-hour `feed_in` values into hourly absolute slots and uses the **arithmetic mean** of the available quarter-hour values inside each local hour. Values are not inverted.

## Command recognition examples

```text
Status code:      \i"status_code":\i\v
Current feed-in:  \i"feedin_current_mchf_kwh":\i\v
h00:              \i"feedin_h00_mchf_kwh":\i\v
h01:              \i"feedin_h01_mchf_kwh":\i\v
h02:              \i"feedin_h02_mchf_kwh":\i\v
...
h20:              \i"feedin_h20_mchf_kwh":\i\v
...
h23:              \i"feedin_h23_mchf_kwh":\i\v
```

Important fixes from the Fable5 architecture review:

- `BKW +20` must not read hour 10. Use `feedin_h20_mchf_kwh`.
- `BKW Aktuell chf/kWh` must read `feedin_current_mchf_kwh`, not the decimal `feedin_current` field when Loxone scaling is 1000 -> 1.
- Missing tariff fields remain `null` when `status_code != 0`; do not convert them to `0`.

## Required status input

Create a nested command recognition for service status:

```text
status-code -> \i"status_code":\i\v
```

Mapping:

```text
0 = ok
1 = no_data
2 = stale
3 = api_error
4 = partial_horizon
5 = unit_unknown
99 = unknown internal state
```

Rule of thumb:

```text
status-code == 0 -> tariff optimization may run
status-code != 0 -> block aggressive EMS/battery optimization and use normal fallback behavior
```

Do not treat missing data as `0`. `0` is a legitimate feed-in price and therefore cannot represent missing data. Das funktioniert sonst vielleicht, aber schön ist anders.

## Poll interval recommendation

```text
15 minutes
```

Reason: Loxone virtual HTTP values should remain fresh within the current hour.

## Optional combined endpoint

For simpler Loxone parsing, current value and status are also available as one semicolon-separated string:

```text
/v1/feedin/current-and-status -> 0;0.081000
```

First field: status code.
Second field: current feed-in value in CHF/kWh.

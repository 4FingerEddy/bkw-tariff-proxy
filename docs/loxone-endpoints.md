# Loxone endpoint mapping

Base URL example:

```text
http://192.168.5.40:8785
```

Current Synology stack mode:

```text
live BKW API data
BKW_TEST_DATA_MODE=off
```

Current live behavior observed on 2026-07-02 before midnight:

```text
status-code -> 4
status      -> partial_horizon
+7...+23    -> numeric live CHF/kWh values
+0...+6     -> unavailable until BKW data covers the current hour
```

This is expected while BKW publishes next-day values but the current day is not yet covered. Do **not** fill missing slots with fake `0`; the optimizer should block aggressive behavior until `status_code == 0`.

For troubleshooting, use `/v1/feedin/relative.json` as the tracking endpoint. It separates the values clearly:

```text
status / status_code              -> effective safety status used by Loxone
source_status                     -> cached service status after the latest refresh
normalized_status                 -> raw/normalizer status of the BKW payload
safe_values_available             -> true only when plain value endpoints may be used
relative[]                        -> diagnostic relative slots; may contain values even when safety status is not OK
```

Example before midnight when BKW already published tomorrow's complete day but the current relative horizon is incomplete:

```json
{
  "status": "partial_horizon",
  "status_code": 4,
  "source_status": "partial_horizon",
  "normalized_status": "ok",
  "effective_status": "partial_horizon",
  "effective_status_code": 4,
  "safe_values_available": false,
  "horizon_hours": 17
}
```

Spotpreis-Optimierer mode:

```text
Relativ
```

## Recommended Loxone template structure

For a reusable Loxone Library/template export, use one parent virtual HTTP input:

```text
Name: BKW Dyntariffs
URL:  http://192.168.5.40:8785
```

Under this parent, create the command recognitions as nested virtual inputs. The root JSON is intentionally flat, so each input can use one unique key.

Prefer the integer `*_mchf_kwh` fields for tariff values. Loxone may highlight JSON decimal values like `0.045` correctly but still evaluate `\v` as `0` because of decimal separator parsing. The integer fields avoid this.

Scale:

```text
mchf_kwh = milli-CHF/kWh
45       = 0.045 CHF/kWh
52       = 0.052 CHF/kWh
```

For the Spotpreis-Optimierer, the scale is fine as-is because the relative ordering is unchanged. For display in CHF/kWh, apply a correction/factor of `0.001` in Loxone.

BKW live data is quarter-hourly. The proxy groups quarter-hour `feed_in` values into hourly relative slots and uses the **arithmetic mean** of the available quarter-hour values inside each hour. This gives the Spotpreis-Optimierer a representative hourly value while keeping the direct BKW CHF/kWh scale.

Command recognition examples:

```text
Status code:      \i"status_code":\i\v
Current feed-in:  \i"feedin_current_mchf_kwh":\i\v
+0:               \i"feedin_relative_00_mchf_kwh":\i\v
+1:               \i"feedin_relative_01_mchf_kwh":\i\v
+2:               \i"feedin_relative_02_mchf_kwh":\i\v
...
+23:              \i"feedin_relative_23_mchf_kwh":\i\v
```

Alternative explicit JSON endpoint, if the root page should ever become more human-oriented:

```text
http://192.168.5.40:8785/v1/loxone.json
```

It returns the same flat Loxone template payload as `/`.

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

Do not treat missing data as `0`. `0` would look like a very attractive feed-in price and could trigger exactly the wrong strategy. Das funktioniert, aber schön ist anders.

## Relative feed-in inputs

Virtual HTTP command recognitions under `BKW Dyntariffs`:

```text
+0  -> \i"feedin_relative_00_mchf_kwh":\i\v
+1  -> \i"feedin_relative_01_mchf_kwh":\i\v
+2  -> \i"feedin_relative_02_mchf_kwh":\i\v
+3  -> \i"feedin_relative_03_mchf_kwh":\i\v
+4  -> \i"feedin_relative_04_mchf_kwh":\i\v
+5  -> \i"feedin_relative_05_mchf_kwh":\i\v
+6  -> \i"feedin_relative_06_mchf_kwh":\i\v
+7  -> \i"feedin_relative_07_mchf_kwh":\i\v
+8  -> \i"feedin_relative_08_mchf_kwh":\i\v
+9  -> \i"feedin_relative_09_mchf_kwh":\i\v
+10 -> \i"feedin_relative_10_mchf_kwh":\i\v
+11 -> \i"feedin_relative_11_mchf_kwh":\i\v
+12 -> \i"feedin_relative_12_mchf_kwh":\i\v
+13 -> \i"feedin_relative_13_mchf_kwh":\i\v
+14 -> \i"feedin_relative_14_mchf_kwh":\i\v
+15 -> \i"feedin_relative_15_mchf_kwh":\i\v
+16 -> \i"feedin_relative_16_mchf_kwh":\i\v
+17 -> \i"feedin_relative_17_mchf_kwh":\i\v
+18 -> \i"feedin_relative_18_mchf_kwh":\i\v
+19 -> \i"feedin_relative_19_mchf_kwh":\i\v
+20 -> \i"feedin_relative_20_mchf_kwh":\i\v
+21 -> \i"feedin_relative_21_mchf_kwh":\i\v
+22 -> \i"feedin_relative_22_mchf_kwh":\i\v
+23 -> \i"feedin_relative_23_mchf_kwh":\i\v
```

Poll interval recommendation:

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

# Loxone endpoint mapping

Base URL example:

```text
http://192.168.5.40:8785
```

Current Synology test stack mode:

```text
synthetic test data
```

Expected while this mode is enabled:

```text
status-code -> 0
+0...+23 -> numeric fake CHF/kWh values
```

These values are for wiring tests only, not real BKW remuneration.

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

Command recognition examples:

```text
Status code:      \i"status_code":\i\v
Current feed-in:  \i"feedin_current":\i\v
+0:               \i"feedin_relative_00":\i\v
+1:               \i"feedin_relative_01":\i\v
+2:               \i"feedin_relative_02":\i\v
...
+23:              \i"feedin_relative_23":\i\v
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
+0  -> \i"feedin_relative_00":\i\v
+1  -> \i"feedin_relative_01":\i\v
+2  -> \i"feedin_relative_02":\i\v
+3  -> \i"feedin_relative_03":\i\v
+4  -> \i"feedin_relative_04":\i\v
+5  -> \i"feedin_relative_05":\i\v
+6  -> \i"feedin_relative_06":\i\v
+7  -> \i"feedin_relative_07":\i\v
+8  -> \i"feedin_relative_08":\i\v
+9  -> \i"feedin_relative_09":\i\v
+10 -> \i"feedin_relative_10":\i\v
+11 -> \i"feedin_relative_11":\i\v
+12 -> \i"feedin_relative_12":\i\v
+13 -> \i"feedin_relative_13":\i\v
+14 -> \i"feedin_relative_14":\i\v
+15 -> \i"feedin_relative_15":\i\v
+16 -> \i"feedin_relative_16":\i\v
+17 -> \i"feedin_relative_17":\i\v
+18 -> \i"feedin_relative_18":\i\v
+19 -> \i"feedin_relative_19":\i\v
+20 -> \i"feedin_relative_20":\i\v
+21 -> \i"feedin_relative_21":\i\v
+22 -> \i"feedin_relative_22":\i\v
+23 -> \i"feedin_relative_23":\i\v
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

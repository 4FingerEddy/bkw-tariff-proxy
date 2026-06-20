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

## Required status input

Create a virtual HTTP input for service status:

```text
status-code -> /v1/status-code
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

Virtual HTTP inputs:

```text
+0  -> /v1/feedin/relative/0
+1  -> /v1/feedin/relative/1
+2  -> /v1/feedin/relative/2
+3  -> /v1/feedin/relative/3
+4  -> /v1/feedin/relative/4
+5  -> /v1/feedin/relative/5
+6  -> /v1/feedin/relative/6
+7  -> /v1/feedin/relative/7
+8  -> /v1/feedin/relative/8
+9  -> /v1/feedin/relative/9
+10 -> /v1/feedin/relative/10
+11 -> /v1/feedin/relative/11
+12 -> /v1/feedin/relative/12
+13 -> /v1/feedin/relative/13
+14 -> /v1/feedin/relative/14
+15 -> /v1/feedin/relative/15
+16 -> /v1/feedin/relative/16
+17 -> /v1/feedin/relative/17
+18 -> /v1/feedin/relative/18
+19 -> /v1/feedin/relative/19
+20 -> /v1/feedin/relative/20
+21 -> /v1/feedin/relative/21
+22 -> /v1/feedin/relative/22
+23 -> /v1/feedin/relative/23
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

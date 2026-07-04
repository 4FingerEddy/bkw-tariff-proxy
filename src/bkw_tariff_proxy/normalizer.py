from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


class TariffNormalizationError(ValueError):
    """Raised when BKW tariff data cannot be safely normalized."""


class TariffPayloadError(TariffNormalizationError):
    """Raised when BKW tariff data has an unexpected shape."""


@dataclass(frozen=True)
class NormalizedSlot:
    offset: int
    value: float
    start: str
    end: str
    interval_count: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "value": self.value,
            "start": self.start,
            "end": self.end,
            "interval_count": self.interval_count,
        }


def normalize_unit_value(value: float | int, unit: str) -> float:
    """Normalize a BKW price component to CHF/kWh.

    We intentionally refuse unknown units. Guessing tariff units is how an EMS
    becomes a slot machine. Nicht wild, aber wir machen es ordentlich.
    """

    normalized_unit = (unit or "").strip().lower().replace(" ", "")
    numeric = float(value)

    if normalized_unit in {"chf/kwh", "chf_kwh", "fr./kwh", "fr/kwh"}:
        return round(numeric, 6)
    if normalized_unit in {"rp/kwh", "rappen/kwh", "ct/kwh", "cents/kwh"}:
        return round(numeric / 100.0, 6)

    raise TariffNormalizationError(f"Unsupported BKW tariff unit: {unit!r}")


def value_to_mchf_kwh(value: float | None) -> int | None:
    if value is None:
        return None
    return int(round(value * 1000))


def _parse_dt(value: str) -> datetime:
    if not value:
        raise TariffPayloadError("Missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise TariffPayloadError(f"Timestamp has no timezone: {value!r}")
    return parsed


def _current_hour(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def _extract_feed_in_component(price: dict[str, Any]) -> tuple[float, str]:
    feed_in = price.get("feed_in") or price.get("feedIn") or []
    if not feed_in:
        raise TariffPayloadError("Price item has no feed_in component")
    component = feed_in[0]
    try:
        return component["value"], component["unit"]
    except KeyError as exc:
        raise TariffPayloadError(f"Price feed_in component misses {exc.args[0]!r}") from exc


def expected_quarter_hours_for_day(day: datetime, tz: ZoneInfo) -> int:
    """Return expected quarter-hour intervals for the local calendar day."""

    local_start = day.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    elapsed = local_end.astimezone(ZoneInfo("UTC")) - local_start.astimezone(ZoneInfo("UTC"))
    return int(elapsed.total_seconds() // 900)


def _empty_hour(hour: int) -> dict[str, Any]:
    return {
        "hour": hour,
        "value_chf_kwh": None,
        "value_mchf_kwh": None,
        "interval_count": 0,
        "dst_placeholder": False,
    }


def normalize_bkw_payload(
    payload: dict[str, Any],
    *,
    now: datetime,
    timezone_name: str = "Europe/Zurich",
    horizon_hours: int = 24,
) -> dict[str, Any]:
    """Normalize a BKW TariffDto-like payload into one local tariff day.

    Productive Loxone values are absolute local day hours h00..h23. Relative
    slots are retained only as a diagnostic view of the received payload.
    Output values are CHF/kWh and are not inverted.
    """

    tz = ZoneInfo(timezone_name)
    prices = payload.get("prices") or []
    publication_timestamp = payload.get("publication_timestamp") or payload.get("publicationTimestamp")
    if not prices:
        return {
            "status": "no_data",
            "unit": "CHF/kWh",
            "publication_timestamp": publication_timestamp,
            "day": None,
            "horizon_hours": 0,
            "relative": [],
        }

    interval_rows: list[dict[str, Any]] = []
    for price in prices:
        start_raw = price.get("start_timestamp") or price.get("startTimestamp")
        end_raw = price.get("end_timestamp") or price.get("endTimestamp")
        start = _parse_dt(start_raw)
        end = _parse_dt(end_raw)
        if end <= start:
            raise TariffPayloadError("Price interval end is not after start")
        value, unit = _extract_feed_in_component(price)
        value_chf = normalize_unit_value(value, unit)
        start_local = start.astimezone(tz)
        interval_rows.append(
            {
                "start": start,
                "end": end,
                "start_local": start_local,
                "date": start_local.date().isoformat(),
                "hour": start_local.hour,
                "value": value_chf,
            }
        )

    dates = sorted({row["date"] for row in interval_rows})
    if len(dates) != 1:
        raise TariffPayloadError(f"Payload spans multiple local tariff dates: {dates}")
    tariff_date = dates[0]
    first_start = min(row["start"] for row in interval_rows)
    last_end = max(row["end"] for row in interval_rows)
    day_start_local = datetime.fromisoformat(tariff_date).replace(tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)
    expected_intervals = expected_quarter_hours_for_day(day_start_local, tz)

    hourly_parts: dict[int, list[dict[str, Any]]] = {hour: [] for hour in range(24)}
    for row in interval_rows:
        hourly_parts[row["hour"]].append(row)

    hours: list[dict[str, Any]] = []
    complete = True
    for hour in range(24):
        parts = sorted(hourly_parts[hour], key=lambda item: item["start"])
        if not parts:
            hours.append(_empty_hour(hour))
            complete = False
            continue
        value = round(sum(part["value"] for part in parts) / len(parts), 6)
        interval_count = len(parts)
        hours.append(
            {
                "hour": hour,
                "value_chf_kwh": value,
                "value_mchf_kwh": value_to_mchf_kwh(value),
                "interval_count": interval_count,
                "dst_placeholder": False,
            }
        )
        if interval_count < 4:
            complete = False

    # Spring-forward day: local 02:00 does not exist. Keep the JSON contract at
    # 24 slots by copying h03 as a flagged placeholder; that hour is never the
    # current clock hour on the affected day.
    if expected_intervals == 92 and not hourly_parts[2] and hourly_parts[3]:
        source = hours[3]
        hours[2] = {
            "hour": 2,
            "value_chf_kwh": source["value_chf_kwh"],
            "value_mchf_kwh": source["value_mchf_kwh"],
            "interval_count": 0,
            "dst_placeholder": True,
        }

    # Fall-back day: 02:00 occurs twice, therefore 8 quarter-hours are expected
    # for that display hour. Normal days need 4 real intervals per hour.
    for hour in range(24):
        if hours[hour]["dst_placeholder"]:
            continue
        expected_for_hour = 8 if expected_intervals == 100 and hour == 2 else 4
        if hours[hour]["interval_count"] != expected_for_hour:
            complete = False

    received_intervals = len(interval_rows)
    if received_intervals != expected_intervals:
        complete = False

    day_payload = {
        "tariff_date": tariff_date,
        "timezone": timezone_name,
        "hours": hours,
        "coverage_start_utc": first_start.astimezone(ZoneInfo("UTC")).isoformat(),
        "coverage_end_utc": last_end.astimezone(ZoneInfo("UTC")).isoformat(),
        "expected_intervals": expected_intervals,
        "received_intervals": received_intervals,
        "content_hash": hashlib.sha256(json.dumps(prices, sort_keys=True).encode("utf-8")).hexdigest(),
        "publication_timestamp": publication_timestamp,
    }

    relative = build_relative_from_days({tariff_date: day_payload}, now=now, timezone_name=timezone_name, horizon_hours=horizon_hours)
    return {
        "status": "ok" if complete else "partial_horizon",
        "unit": "CHF/kWh",
        "publication_timestamp": publication_timestamp,
        "day": day_payload,
        "horizon_hours": len(relative),
        "relative": [slot.as_dict() for slot in relative],
    }


def build_relative_from_days(
    days: dict[str, dict[str, Any]],
    *,
    now: datetime,
    timezone_name: str = "Europe/Zurich",
    horizon_hours: int = 24,
) -> list[NormalizedSlot]:
    """Build a rolling diagnostic horizon from stored absolute day datasets."""

    tz = ZoneInfo(timezone_name)
    base_local = _current_hour(now.astimezone(tz))
    slots: list[NormalizedSlot] = []
    for offset in range(horizon_hours):
        local_start = base_local + timedelta(hours=offset)
        day = days.get(local_start.date().isoformat())
        if not day:
            continue
        hour = day["hours"][local_start.hour]
        value = hour.get("value_chf_kwh")
        if value is None:
            continue
        local_end = local_start + timedelta(hours=1)
        slots.append(
            NormalizedSlot(
                offset=offset,
                value=value,
                start=local_start.astimezone(ZoneInfo("UTC")).isoformat(),
                end=local_end.astimezone(ZoneInfo("UTC")).isoformat(),
                interval_count=int(hour.get("interval_count") or 0),
            )
        )
    return slots

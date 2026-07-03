from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


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


def normalize_bkw_payload(
    payload: dict[str, Any],
    *,
    now: datetime,
    horizon_hours: int = 24,
) -> dict[str, Any]:
    """Normalize a BKW TariffDto-like payload for Loxone relative inputs.

    Output values are CHF/kWh and are not inverted.
    """

    prices = payload.get("prices") or []
    if not prices:
        return {
            "status": "no_data",
            "unit": "CHF/kWh",
            "publication_timestamp": payload.get("publication_timestamp"),
            "horizon_hours": 0,
            "relative": [],
        }

    base = _current_hour(now)
    hourly: dict[int, list[NormalizedSlot]] = {}

    for price in prices:
        start_raw = price.get("start_timestamp") or price.get("startTimestamp")
        end_raw = price.get("end_timestamp") or price.get("endTimestamp")
        start = _parse_dt(start_raw)
        end = _parse_dt(end_raw)

        # Include the interval covering the current hour, then future intervals.
        if end <= base:
            continue

        offset = int((start.replace(minute=0, second=0, microsecond=0) - base) / timedelta(hours=1))
        if offset < 0 or offset >= horizon_hours:
            continue

        value, unit = _extract_feed_in_component(price)
        slot = NormalizedSlot(
            offset=offset,
            value=normalize_unit_value(value, unit),
            start=start.isoformat(),
            end=end.isoformat(),
        )
        hourly.setdefault(offset, []).append(slot)

    slots: list[NormalizedSlot] = []
    for offset in sorted(hourly):
        parts = sorted(hourly[offset], key=lambda slot: slot.start)
        # BKW live data is quarter-hourly. Loxone receives hourly relative slots.
        # Use the arithmetic mean of all feed-in values within the hour so the
        # Spotpreis-Optimierer receives the representative hourly remuneration.
        slots.append(
            NormalizedSlot(
                offset=offset,
                value=round(sum(slot.value for slot in parts) / len(parts), 6),
                start=parts[0].start,
                end=parts[-1].end,
                interval_count=len(parts),
            )
        )

    return {
        "status": "ok" if slots else "no_data",
        "unit": "CHF/kWh",
        "publication_timestamp": payload.get("publication_timestamp") or payload.get("publicationTimestamp"),
        "horizon_hours": len(slots),
        "min_interval_count": min((slot.interval_count for slot in slots), default=0),
        "relative": [slot.as_dict() for slot in slots],
    }

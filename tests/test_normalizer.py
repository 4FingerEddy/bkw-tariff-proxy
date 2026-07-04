import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bkw_tariff_proxy.normalizer import (
    TariffNormalizationError,
    normalize_bkw_payload,
    normalize_unit_value,
)

TZ = ZoneInfo("Europe/Zurich")


def make_day_payload(day: str, *, missing: int = 0, unit: str = "CHF_kWh", base_value: float = 0.0):
    start = datetime.fromisoformat(day).replace(tzinfo=TZ)
    prices = []
    for index in range(96 - missing):
        interval_start = start + timedelta(minutes=15 * index)
        hour = interval_start.hour
        value = round(base_value + hour / 1000, 6)
        prices.append(
            {
                "start_timestamp": interval_start.astimezone(ZoneInfo("UTC")).isoformat(),
                "end_timestamp": (interval_start + timedelta(minutes=15)).astimezone(ZoneInfo("UTC")).isoformat(),
                "feed_in": [{"unit": unit, "value": value}],
            }
        )
    return {"publication_timestamp": f"{day}T12:00:00Z", "prices": prices}


class UnitNormalizationTests(unittest.TestCase):
    def test_passes_through_chf_per_kwh(self):
        self.assertEqual(normalize_unit_value(0.081, "CHF/kWh"), 0.081)

    def test_converts_rappen_per_kwh_to_chf_per_kwh(self):
        self.assertEqual(normalize_unit_value(8.1, "Rp/kWh"), 0.081)

    def test_rejects_unknown_units_instead_of_guessing(self):
        with self.assertRaises(TariffNormalizationError):
            normalize_unit_value(81, "mystery")

    def test_accepts_bkw_chf_underscore_unit(self):
        self.assertEqual(normalize_unit_value(0.092, "CHF_kWh"), 0.092)


class BkwPayloadNormalizationTests(unittest.TestCase):
    def test_builds_absolute_local_day_vector(self):
        normalized = normalize_bkw_payload(
            make_day_payload("2026-07-04"),
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["status"], "ok")
        self.assertEqual(normalized["day"]["tariff_date"], "2026-07-04")
        self.assertEqual(len(normalized["day"]["hours"]), 24)
        self.assertEqual(normalized["day"]["hours"][0]["value_chf_kwh"], 0.0)
        self.assertEqual(normalized["day"]["hours"][12]["value_chf_kwh"], 0.012)
        self.assertEqual(normalized["day"]["hours"][12]["value_mchf_kwh"], 12)
        self.assertEqual(normalized["day"]["hours"][12]["interval_count"], 4)

    def test_relative_is_diagnostic_rest_of_day_not_productive_status(self):
        normalized = normalize_bkw_payload(
            make_day_payload("2026-07-04"),
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["status"], "ok")
        self.assertEqual(normalized["horizon_hours"], 16)
        self.assertEqual(normalized["relative"][0]["offset"], 0)
        self.assertEqual(normalized["relative"][0]["value"], 0.008)

    def test_marks_partial_when_intervals_are_missing(self):
        normalized = normalize_bkw_payload(
            make_day_payload("2026-07-04", missing=1),
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["status"], "partial_horizon")
        self.assertEqual(normalized["day"]["received_intervals"], 95)
        self.assertEqual(normalized["day"]["hours"][23]["interval_count"], 3)

    def test_preserves_negative_values_and_integer_scale(self):
        normalized = normalize_bkw_payload(
            make_day_payload("2026-07-04", base_value=-0.011),
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["day"]["hours"][0]["value_chf_kwh"], -0.011)
        self.assertEqual(normalized["day"]["hours"][0]["value_mchf_kwh"], -11)

    def test_marks_no_data_when_price_list_is_empty(self):
        normalized = normalize_bkw_payload(
            {"publication_timestamp": None, "prices": []},
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )
        self.assertEqual(normalized["status"], "no_data")
        self.assertEqual(normalized["relative"], [])
        self.assertIsNone(normalized["day"])


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timezone

from bkw_tariff_proxy.normalizer import (
    TariffNormalizationError,
    normalize_unit_value,
    normalize_bkw_payload,
)


class UnitNormalizationTests(unittest.TestCase):
    def test_passes_through_chf_per_kwh(self):
        self.assertEqual(normalize_unit_value(0.081, "CHF/kWh"), 0.081)

    def test_converts_rappen_per_kwh_to_chf_per_kwh(self):
        self.assertEqual(normalize_unit_value(8.1, "Rp/kWh"), 0.081)

    def test_rejects_unknown_units_instead_of_guessing(self):
        with self.assertRaises(TariffNormalizationError):
            normalize_unit_value(81, "mystery")


class BkwPayloadNormalizationTests(unittest.TestCase):
    def test_extracts_feed_in_prices_and_relative_slots(self):
        payload = {
            "publication_timestamp": "2026-07-01T13:00:00+02:00",
            "prices": [
                {
                    "start_timestamp": "2026-07-01T14:00:00+02:00",
                    "end_timestamp": "2026-07-01T15:00:00+02:00",
                    "feed_in": [{"unit": "Rp/kWh", "value": 8.1}],
                },
                {
                    "start_timestamp": "2026-07-01T15:00:00+02:00",
                    "end_timestamp": "2026-07-01T16:00:00+02:00",
                    "feed_in": [{"unit": "Rp/kWh", "value": 7.7}],
                },
            ],
        }
        normalized = normalize_bkw_payload(
            payload,
            now=datetime.fromisoformat("2026-07-01T14:05:00+02:00"),
        )
        self.assertEqual(normalized["status"], "ok")
        self.assertEqual(normalized["unit"], "CHF/kWh")
        self.assertEqual(normalized["publication_timestamp"], "2026-07-01T13:00:00+02:00")
        self.assertEqual(normalized["relative"][0]["offset"], 0)
        self.assertEqual(normalized["relative"][0]["value"], 0.081)
        self.assertEqual(normalized["relative"][1]["offset"], 1)
        self.assertEqual(normalized["relative"][1]["value"], 0.077)

    def test_groups_quarter_hour_feed_in_prices_to_one_conservative_hourly_slot(self):
        payload = {
            "publication_timestamp": "2026-07-02T15:35:00Z",
            "prices": [
                {
                    "start_timestamp": "2026-07-03T00:00:00+02:00",
                    "end_timestamp": "2026-07-03T00:15:00+02:00",
                    "feed_in": [{"unit": "CHF_kWh", "value": 0.092}],
                },
                {
                    "start_timestamp": "2026-07-03T00:15:00+02:00",
                    "end_timestamp": "2026-07-03T00:30:00+02:00",
                    "feed_in": [{"unit": "CHF_kWh", "value": 0.087}],
                },
                {
                    "start_timestamp": "2026-07-03T00:30:00+02:00",
                    "end_timestamp": "2026-07-03T00:45:00+02:00",
                    "feed_in": [{"unit": "CHF_kWh", "value": 0.095}],
                },
                {
                    "start_timestamp": "2026-07-03T00:45:00+02:00",
                    "end_timestamp": "2026-07-03T01:00:00+02:00",
                    "feed_in": [{"unit": "CHF_kWh", "value": 0.089}],
                },
                {
                    "start_timestamp": "2026-07-03T01:00:00+02:00",
                    "end_timestamp": "2026-07-03T01:15:00+02:00",
                    "feed_in": [{"unit": "CHF_kWh", "value": 0.101}],
                },
            ],
        }
        normalized = normalize_bkw_payload(
            payload,
            now=datetime.fromisoformat("2026-07-03T00:05:00+02:00"),
        )
        self.assertEqual(normalized["status"], "ok")
        self.assertEqual(normalized["horizon_hours"], 2)
        self.assertEqual(normalized["relative"][0]["offset"], 0)
        self.assertEqual(normalized["relative"][0]["value"], 0.087)
        self.assertEqual(normalized["relative"][0]["interval_count"], 4)
        self.assertEqual(normalized["relative"][1]["offset"], 1)
        self.assertEqual(normalized["relative"][1]["value"], 0.101)
        self.assertEqual(normalized["relative"][1]["interval_count"], 1)

    def test_accepts_bkw_chf_underscore_unit(self):
        self.assertEqual(normalize_unit_value(0.092, "CHF_kWh"), 0.092)

    def test_marks_no_data_when_price_list_is_empty(self):
        normalized = normalize_bkw_payload(
            {"publication_timestamp": None, "prices": []},
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(normalized["status"], "no_data")
        self.assertEqual(normalized["relative"], [])


if __name__ == "__main__":
    unittest.main()

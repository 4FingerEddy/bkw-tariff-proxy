import unittest
from datetime import datetime, timedelta, timezone
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


def make_day_payload_without_hours(day: str, missing_hours: set[int], *, unit: str = "CHF_kWh", base_value: float = 0.0):
    start = datetime.fromisoformat(day).replace(tzinfo=TZ)
    prices = []
    for index in range(96):
        interval_start = start + timedelta(minutes=15 * index)
        hour = interval_start.hour
        if hour in missing_hours:
            continue
        value = round(base_value + hour / 1000, 6)
        prices.append(
            {
                "start_timestamp": interval_start.astimezone(ZoneInfo("UTC")).isoformat(),
                "end_timestamp": (interval_start + timedelta(minutes=15)).astimezone(ZoneInfo("UTC")).isoformat(),
                "feed_in": [{"unit": unit, "value": value}],
            }
        )
    return {"publication_timestamp": f"{day}T12:00:00Z", "prices": prices}


def make_dst_day_payload(day: str, *, missing_hours: set[int] | None = None):
    missing_hours = missing_hours or set()
    local_start = datetime.fromisoformat(day).replace(tzinfo=TZ)
    local_end = local_start + timedelta(days=1)
    interval_start = local_start.astimezone(timezone.utc)
    interval_end = local_end.astimezone(timezone.utc)
    prices = []
    while interval_start < interval_end:
        local_hour = interval_start.astimezone(TZ).hour
        if local_hour not in missing_hours:
            prices.append(
                {
                    "start_timestamp": interval_start.isoformat(),
                    "end_timestamp": (interval_start + timedelta(minutes=15)).isoformat(),
                    "feed_in": [{"unit": "CHF_kWh", "value": round(0.04 + local_hour / 1000, 6)}],
                }
            )
        interval_start += timedelta(minutes=15)
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

    def test_zero_fills_one_incomplete_hour(self):
        normalized = normalize_bkw_payload(
            make_day_payload("2026-07-04", missing=1),
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["status"], "single_missing_hour_zero_filled")
        self.assertEqual(normalized["status_code"], 10)
        self.assertEqual(normalized["data_quality_status"], "single_missing_hour_zero_filled")
        self.assertNotIn("quality_status_code", normalized)
        self.assertEqual(normalized["day"]["received_intervals"], 95)
        self.assertEqual(normalized["day"]["hours"][23]["interval_count"], 0)
        self.assertEqual(normalized["day"]["hours"][23]["value_chf_kwh"], 0.0)
        self.assertEqual(normalized["day"]["missing_hours"], [23])

    def test_zero_fills_one_missing_hour_and_reports_code_10(self):
        normalized = normalize_bkw_payload(
            make_day_payload_without_hours("2026-07-04", {14}),
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["status"], "single_missing_hour_zero_filled")
        self.assertEqual(normalized["status_code"], 10)
        self.assertEqual(normalized["data_quality_status"], "single_missing_hour_zero_filled")
        self.assertNotIn("quality_status_code", normalized)
        self.assertEqual(normalized["day"]["missing_hours"], [14])
        self.assertEqual(normalized["day"]["missing_hour_count"], 1)
        self.assertEqual(normalized["day"]["zero_filled_hours"], [14])
        self.assertEqual(normalized["day"]["hours"][14]["value_chf_kwh"], 0.0)
        self.assertEqual(normalized["day"]["hours"][14]["value_mchf_kwh"], 0)
        self.assertTrue(normalized["day"]["hours"][14]["zero_filled"])

    def test_marks_partial_when_more_than_one_hour_is_missing(self):
        normalized = normalize_bkw_payload(
            make_day_payload_without_hours("2026-07-04", {14, 15}),
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["status"], "partial_horizon")
        self.assertEqual(normalized["data_quality_status"], "partial_horizon")
        self.assertEqual(normalized["day"]["missing_hours"], [14, 15])
        self.assertEqual(normalized["day"]["missing_hour_count"], 2)
        self.assertEqual(normalized["day"]["zero_filled_hours"], [])
        self.assertIsNone(normalized["day"]["hours"][14]["value_chf_kwh"])

    def test_complete_spring_forward_day_is_ok(self):
        normalized = normalize_bkw_payload(
            make_dst_day_payload("2026-03-29"),
            now=datetime.fromisoformat("2026-03-29T12:00:00+02:00"),
        )

        self.assertEqual(normalized["day"]["expected_intervals"], 92)
        self.assertEqual(normalized["day"]["received_intervals"], 92)
        self.assertTrue(normalized["day"]["hours"][2]["dst_placeholder"])
        self.assertEqual(normalized["status"], "ok")
        self.assertEqual(normalized["status_code"], 0)

    def test_complete_fall_back_day_is_ok(self):
        normalized = normalize_bkw_payload(
            make_dst_day_payload("2026-10-25"),
            now=datetime.fromisoformat("2026-10-25T12:00:00+01:00"),
        )

        self.assertEqual(normalized["day"]["expected_intervals"], 100)
        self.assertEqual(normalized["day"]["received_intervals"], 100)
        self.assertEqual(normalized["day"]["hours"][2]["interval_count"], 8)
        self.assertEqual(normalized["status"], "ok")
        self.assertEqual(normalized["status_code"], 0)

    def test_single_missing_hour_is_zero_filled_on_dst_days(self):
        for day, now, expected_intervals in [
            ("2026-03-29", "2026-03-29T12:00:00+02:00", 92),
            ("2026-10-25", "2026-10-25T12:00:00+01:00", 100),
        ]:
            with self.subTest(day=day):
                normalized = normalize_bkw_payload(
                    make_dst_day_payload(day, missing_hours={14}),
                    now=datetime.fromisoformat(now),
                )

                self.assertEqual(normalized["day"]["expected_intervals"], expected_intervals)
                self.assertEqual(normalized["day"]["missing_hours"], [14])
                self.assertEqual(normalized["day"]["zero_filled_hours"], [14])
                self.assertEqual(normalized["day"]["hours"][14]["value_mchf_kwh"], 0)
                self.assertEqual(normalized["status"], "single_missing_hour_zero_filled")
                self.assertEqual(normalized["status_code"], 10)

    def test_fall_back_repeated_hour_can_be_zero_filled_with_eight_missing_intervals(self):
        normalized = normalize_bkw_payload(
            make_dst_day_payload("2026-10-25", missing_hours={2}),
            now=datetime.fromisoformat("2026-10-25T12:00:00+01:00"),
        )

        self.assertEqual(normalized["day"]["expected_intervals"], 100)
        self.assertEqual(normalized["day"]["received_intervals"], 92)
        self.assertEqual(normalized["day"]["missing_hours"], [2])
        self.assertEqual(normalized["day"]["zero_filled_hours"], [2])
        self.assertEqual(normalized["day"]["hours"][2]["interval_count"], 0)
        self.assertEqual(normalized["status"], "single_missing_hour_zero_filled")
        self.assertEqual(normalized["status_code"], 10)

    def test_fall_back_repeated_hour_accepts_five_interval_deficit(self):
        payload = make_dst_day_payload("2026-10-25")
        retained = []
        removed = 0
        for price in payload["prices"]:
            local_hour = datetime.fromisoformat(price["start_timestamp"]).astimezone(TZ).hour
            if local_hour == 2 and removed < 5:
                removed += 1
                continue
            retained.append(price)
        payload["prices"] = retained

        normalized = normalize_bkw_payload(
            payload,
            now=datetime.fromisoformat("2026-10-25T12:00:00+01:00"),
        )

        self.assertEqual(removed, 5)
        self.assertEqual(normalized["day"]["received_intervals"], 95)
        self.assertEqual(normalized["day"]["zero_filled_hours"], [2])
        self.assertEqual(normalized["status_code"], 10)

    def test_spring_placeholder_refreshes_when_hour_three_is_zero_filled(self):
        payload = make_dst_day_payload("2026-03-29")
        for index, price in enumerate(payload["prices"]):
            local_hour = datetime.fromisoformat(price["start_timestamp"]).astimezone(TZ).hour
            if local_hour == 3:
                del payload["prices"][index]
                break

        normalized = normalize_bkw_payload(
            payload,
            now=datetime.fromisoformat("2026-03-29T12:00:00+02:00"),
        )

        self.assertEqual(normalized["status_code"], 10)
        self.assertEqual(normalized["day"]["zero_filled_hours"], [3])
        self.assertTrue(normalized["day"]["hours"][2]["dst_placeholder"])
        self.assertEqual(normalized["day"]["hours"][2]["value_chf_kwh"], 0.0)
        self.assertEqual(normalized["day"]["hours"][2]["value_mchf_kwh"], 0)

    def test_overfull_hour_is_not_treated_as_missing(self):
        payload = make_day_payload("2026-07-04")
        duplicate = dict(payload["prices"][56])
        duplicate["feed_in"] = [dict(payload["prices"][56]["feed_in"][0])]
        payload["prices"].append(duplicate)

        normalized = normalize_bkw_payload(
            payload,
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["day"]["received_intervals"], 97)
        self.assertEqual(normalized["day"]["missing_hours"], [14])
        self.assertEqual(normalized["day"]["zero_filled_hours"], [])
        self.assertEqual(normalized["status"], "partial_horizon")
        self.assertEqual(normalized["status_code"], 4)

    def test_duplicate_replacing_a_missing_interval_fails_closed(self):
        payload = make_day_payload("2026-07-04")
        duplicate = dict(payload["prices"][56])
        duplicate["feed_in"] = [dict(payload["prices"][56]["feed_in"][0])]
        payload["prices"][57] = duplicate

        normalized = normalize_bkw_payload(
            payload,
            now=datetime.fromisoformat("2026-07-04T08:30:00+02:00"),
        )

        self.assertEqual(normalized["day"]["received_intervals"], 96)
        self.assertEqual(normalized["day"]["duplicate_hours"], [14])
        self.assertEqual(normalized["day"]["duplicate_interval_count"], 1)
        self.assertEqual(normalized["status"], "partial_horizon")
        self.assertEqual(normalized["status_code"], 4)

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

from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from app.observed_climate_generation import (
    DailyObservation,
    calculate_daily_mean_thi,
    period_file_name,
    summarize_observed_period,
)
from scripts.fetch_jma_observations import parse_daily_html


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/jma_chiba_daily_2024_09.html"


class ObservedClimateGenerationTest(unittest.TestCase):
    def test_thi_formula_matches_the_nrc_daily_mean_formula(self) -> None:
        calculated = calculate_daily_mean_thi(25.0, 70.0)
        nrc = (1.8 * 25.0 + 32) - (0.55 - 0.0055 * 70.0) * (1.8 * 25.0 - 26)

        self.assertAlmostEqual(calculated, nrc, places=10)

    def test_html_fixture_preserves_values_quality_marks_and_missing_humidity(self) -> None:
        rows = parse_daily_html(
            FIXTURE.read_text(encoding="utf-8"),
            year=2024,
            month=9,
            source_url="https://example.invalid/jma",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].observed_on, date(2024, 9, 1))
        self.assertEqual(rows[0].mean_temperature_c, 27.0)
        self.assertEqual(rows[0].mean_relative_humidity_pct, 79.0)
        self.assertEqual(rows[0].temperature_quality_mark, ")")
        self.assertIsNotNone(rows[0].thi)
        self.assertIsNone(rows[1].mean_relative_humidity_pct)
        self.assertIsNone(rows[1].thi)

    def test_missing_thi_is_reported_as_a_range_instead_of_silent_pass(self) -> None:
        rows = (
            DailyObservation(
                observed_on=date(2024, 1, 1),
                mean_temperature_c=25.0,
                mean_relative_humidity_pct=70.0,
                thi=calculate_daily_mean_thi(25.0, 70.0),
            ),
            DailyObservation(
                observed_on=date(2024, 1, 2),
                mean_temperature_c=24.0,
                mean_relative_humidity_pct=None,
                thi=None,
            ),
        )

        summary = summarize_observed_period(
            rows,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            threshold=72.0,
        )

        self.assertFalse(summary.is_complete)
        self.assertEqual(summary.expected_days, 2)
        self.assertEqual(summary.valid_thi_days, 1)
        self.assertEqual(summary.missing_observation_dates, ())
        self.assertEqual(summary.missing_thi_dates, (date(2024, 1, 2),))
        self.assertEqual(summary.thi_days_lower_bound, 1)
        self.assertEqual(summary.thi_days_upper_bound, 2)

    def test_missing_calendar_date_is_distinguished_from_missing_weather_value(self) -> None:
        rows = (
            DailyObservation(
                observed_on=date(2024, 1, 1),
                mean_temperature_c=25.0,
                mean_relative_humidity_pct=70.0,
                thi=calculate_daily_mean_thi(25.0, 70.0),
            ),
        )

        summary = summarize_observed_period(
            rows,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            threshold=72.0,
        )

        self.assertEqual(summary.missing_observation_dates, (date(2024, 1, 2),))
        self.assertEqual(summary.missing_thi_dates, ())
        self.assertEqual(summary.thi_days_upper_bound, 2)

    def test_output_file_name_uses_the_requested_period(self) -> None:
        self.assertEqual(
            period_file_name("jma_chiba_daily", 2024, 2024, "csv"),
            "jma_chiba_daily_2024_2024.csv",
        )
        self.assertEqual(
            period_file_name("jma_chiba_daily", 2020, 2025, "csv"),
            "jma_chiba_daily_2020_2025.csv",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DataLayoutTest(unittest.TestCase):
    def test_observed_and_derived_files_have_matching_time_granularity(self) -> None:
        hourly_paths = (
            "data/observed/jma_chiba_2024_08_17_hourly.csv",
            "data/derived/jma_chiba_2024_08_17_hourly_thi.csv",
            "data/derived/chiba_demo_future_plus1c_hourly.csv",
            "data/derived/chiba_demo_future_plus2c_hourly.csv",
        )
        for relative_path in hourly_paths:
            with (ROOT / relative_path).open(encoding="utf-8-sig", newline="") as source:
                self.assertEqual(next(csv.reader(source))[0], "timestamp_jst")
        with (ROOT / "data/observed/jma_chiba_2024_08_daily.csv").open(encoding="utf-8-sig", newline="") as source:
            self.assertEqual(next(csv.reader(source))[0], "date")

    def test_generated_climate_profile_is_a_bounded_scenario(self) -> None:
        profile = json.loads((ROOT / "data/climate_profiles/generated/chiba_city_2025_2034.json").read_text())
        self.assertEqual(profile["period"], {"start_year": 2025, "end_year": 2034})
        self.assertGreaterEqual(len(profile["years"]["2030"]["model_values"]), 4)

    def test_recent_jma_baseline_has_every_calendar_day_and_explicit_thi_gaps(self) -> None:
        daily_path = ROOT / "data/observed/jma_chiba_daily_2020_2025.csv"
        with daily_path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))

        self.assertEqual(len(rows), 2192)
        self.assertEqual(rows[0]["date"], "2020-01-01")
        self.assertEqual(rows[-1]["date"], "2025-12-31")
        self.assertEqual(len({row["date"] for row in rows}), 2192)
        self.assertEqual(
            [row["date"] for row in rows if not row["thi_daily_mean"]],
            ["2022-09-19", "2022-09-20", "2022-09-21"],
        )

        summary = json.loads(
            (ROOT / "data/observed/jma_chiba_thi_summary_2020_2025.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(summary["period"], {"start_year": 2020, "end_year": 2025})
        self.assertEqual(summary["classification"], "official_observation")
        self.assertEqual(
            summary["period_summary"]["annual_mean_thi_days_lower_bound"], 97.0
        )
        self.assertEqual(
            summary["period_summary"]["annual_mean_thi_days_upper_bound"], 97.5
        )

    def test_recent_cmip6_baseline_is_complete_and_pairable_with_future_models(self) -> None:
        baseline = json.loads(
            (
                ROOT
                / "data/climate_profiles/generated/chiba_city_2020_2025.json"
            ).read_text(encoding="utf-8")
        )
        future = json.loads(
            (
                ROOT
                / "data/climate_profiles/generated/chiba_city_2025_2034.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(baseline["period"], {"start_year": 2020, "end_year": 2025})
        self.assertEqual(baseline["period_role"], "recent_model_baseline")
        self.assertEqual(baseline["source"]["provenance_kind"], "processed_cmip6_api")
        self.assertEqual(set(baseline["years"]), {str(year) for year in range(2020, 2026)})
        for year, year_data in baseline["years"].items():
            expected_days = 366 if date(int(year), 12, 31).timetuple().tm_yday == 366 else 365
            self.assertGreaterEqual(len(year_data["model_values"]), 4)
            self.assertTrue(
                all(
                    model["valid_daily_values"] == expected_days
                    for model in year_data["model_values"].values()
                )
            )

        baseline_models = set.intersection(
            *(set(year["model_values"]) for year in baseline["years"].values())
        )
        future_models = set.intersection(
            *(set(year["model_values"]) for year in future["years"].values())
        )
        self.assertGreaterEqual(len(baseline_models & future_models), 4)
        self.assertEqual(
            baseline["thi_definition"]["formula"], future["thi_definition"]["formula"]
        )
        self.assertEqual(
            baseline["thi_definition"]["threshold"], future["thi_definition"]["threshold"]
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
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


if __name__ == "__main__":
    unittest.main()

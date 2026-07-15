from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import unittest

from app.climate_profile import (
    ClimateProfileError,
    load_climate_profile,
    summarize_thi_days,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "data/climate_profiles/generated/chiba_city_2025_2034.json"


class ClimateProfileTest(unittest.TestCase):
    def test_period_summary_averages_each_model_before_comparing_models(self) -> None:
        profile = {
            "region_name_ja": "テスト地域",
            "period": {"start_year": 2026, "end_year": 2027},
            "thi_definition": {"threshold": 72},
            "source": {"provider": "test", "dataset": "fixture"},
            "years": {
                "2026": {
                    "model_values": {
                        "cool": {"thi_days_daily_mean_ge_72": 80},
                        "middle": {"thi_days_daily_mean_ge_72": 100},
                        "hot": {"thi_days_daily_mean_ge_72": 120},
                    }
                },
                "2027": {
                    "model_values": {
                        "cool": {"thi_days_daily_mean_ge_72": 90},
                        "middle": {"thi_days_daily_mean_ge_72": 110},
                        "hot": {"thi_days_daily_mean_ge_72": 130},
                    }
                },
            },
        }

        summary = summarize_thi_days(profile, 2026, 2027)

        self.assertEqual(summary.region_name_ja, "テスト地域")
        self.assertEqual(summary.start_year, 2026)
        self.assertEqual(summary.end_year, 2027)
        self.assertEqual(summary.thi_threshold, Decimal("72"))
        self.assertEqual(summary.model_count, 3)
        self.assertEqual(summary.median_annual_days, Decimal("105"))
        self.assertEqual(summary.minimum_annual_days, Decimal("85"))
        self.assertEqual(summary.maximum_annual_days, Decimal("125"))
        self.assertEqual(summary.model_annual_days["middle"], Decimal("105"))

    def test_saved_profile_returns_bounded_period_summaries(self) -> None:
        profile = load_climate_profile(PROFILE_PATH)

        near_future = summarize_thi_days(profile, 2026, 2030)
        later = summarize_thi_days(profile, 2031, 2034)

        self.assertEqual(near_future.model_count, 6)
        self.assertEqual(near_future.median_annual_days, Decimal("96.2"))
        self.assertEqual(near_future.minimum_annual_days, Decimal("81.6"))
        self.assertEqual(near_future.maximum_annual_days, Decimal("102.6"))
        self.assertEqual(later.median_annual_days, Decimal("98.375"))
        self.assertEqual(later.minimum_annual_days, Decimal("86.5"))
        self.assertEqual(later.maximum_annual_days, Decimal("102.75"))

    def test_period_outside_saved_years_is_not_extrapolated(self) -> None:
        profile = load_climate_profile(PROFILE_PATH)

        with self.assertRaisesRegex(ClimateProfileError, "未取得"):
            summarize_thi_days(profile, 2031, 2035)

    def test_missing_common_models_are_rejected(self) -> None:
        profile = {
            "region_name_ja": "テスト地域",
            "period": {"start_year": 2026, "end_year": 2027},
            "thi_definition": {"threshold": 72},
            "source": {"provider": "test", "dataset": "fixture"},
            "years": {
                "2026": {"model_values": {"a": {"thi_days_daily_mean_ge_72": 80}}},
                "2027": {"model_values": {"b": {"thi_days_daily_mean_ge_72": 90}}},
            },
        }

        with self.assertRaisesRegex(ClimateProfileError, "共通モデル"):
            summarize_thi_days(profile, 2026, 2027)

    def test_invalid_day_count_is_rejected(self) -> None:
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        profile["years"]["2026"]["model_values"]["CMCC_CM2_VHR4"][
            "thi_days_daily_mean_ge_72"
        ] = -1

        with self.assertRaisesRegex(ClimateProfileError, "0〜366"):
            summarize_thi_days(profile, 2026, 2030)


if __name__ == "__main__":
    unittest.main()

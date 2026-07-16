from __future__ import annotations

from decimal import Decimal
import re
import unittest

from fastapi.testclient import TestClient

from app.main import _dashboard, app


class ClimateBackgroundViewTest(unittest.TestCase):
    def test_saved_thi_periods_are_separate_from_fan_counts(self) -> None:
        dashboard = _dashboard(60, 2, 10, None, 2026)
        climate = dashboard["climate_background"]

        self.assertTrue(climate["available"])
        self.assertEqual(climate["region_name_ja"], "千葉市")
        self.assertEqual(climate["thi_threshold"], 72.0)
        self.assertEqual(climate["operating_hours_per_day"], 24.0)
        self.assertEqual(climate["observed_baseline"]["start_year"], 2020)
        self.assertEqual(climate["observed_baseline"]["end_year"], 2025)
        self.assertEqual(climate["observed_baseline"]["lower_annual_days"], 97.0)
        self.assertEqual(climate["observed_baseline"]["upper_annual_days"], 97.5)
        self.assertEqual(len(climate["periods"]), 2)

        near_future = climate["periods"][0]
        self.assertEqual(near_future["start_year"], 2026)
        self.assertEqual(near_future["end_year"], 2030)
        self.assertEqual(near_future["model_count"], 6)
        self.assertAlmostEqual(near_future["median_change_days"], 7.3166666667)
        self.assertAlmostEqual(near_future["central_lower_days"], 104.3166666667)
        self.assertAlmostEqual(near_future["central_upper_days"], 104.8166666667)
        self.assertAlmostEqual(near_future["median_annual_days"], 104.5666666667)
        self.assertAlmostEqual(near_future["minimum_annual_days"], 95.5333333333)
        self.assertAlmostEqual(near_future["maximum_annual_days"], 108.9333333333)
        self.assertEqual(near_future["raw_model_median_annual_days"], 96.2)
        self.assertEqual(near_future["raw_model_minimum_annual_days"], 81.6)
        self.assertEqual(near_future["raw_model_maximum_annual_days"], 102.6)

        first_phase_cost = near_future["plans"][0]
        self.assertEqual(first_phase_cost["additional_fan_count"], 5)
        self.assertEqual(first_phase_cost["annual_electricity_median_yen"], 132839)
        self.assertEqual(first_phase_cost["annual_electricity_minimum_yen"], 124058)
        self.assertEqual(first_phase_cost["annual_electricity_maximum_yen"], 137083)

        self.assertEqual(
            dashboard["navigation"].plans[1].additional_fan_count,
            5,
            "THI must not change the first-phase fan count",
        )
        self.assertEqual(
            dashboard["navigation"].plans[2].additional_fan_count,
            10,
            "THI must not change the headcount-guideline fan count",
        )

    def test_screen_explains_thi_uncertainty_and_cost_connection(self) -> None:
        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("将来の暑熱期間は、運転日数と電力費の背景です", response.text)
        self.assertIn("現在相当（2020〜2025年観測）", response.text)
        self.assertIn("97〜98日／年", response.text)
        self.assertIn("2026〜2030年", response.text)
        self.assertIn("観測基準に揃えた中心目安</dt><dd>104〜105日／年", response.text)
        self.assertIn("モデル差を含む範囲</dt><dd>96〜109日／年", response.text)
        self.assertIn("現在比（変化量中央値）</dt><dd>+7日／年", response.text)
        self.assertIn("2031〜2034年", response.text)
        self.assertIn("観測基準に揃えた中心目安</dt><dd>105〜106日／年", response.text)
        self.assertIn("モデル差を含む範囲</dt><dd>99〜110日／年", response.text)
        self.assertIn("生のCMIP6期間値：中央値96日、範囲82〜103日／年", response.text)
        self.assertIn("2035年以降は未取得", response.text)
        self.assertIn("日平均THI 72以上", response.text)
        self.assertIn("確定予報ではありません", response.text)
        self.assertIn("ファン台数や投資年は変更しません", response.text)
        self.assertIn("1対象日あたり24時間", response.text)
        self.assertIn("第1期：小さく始める（5台追加）", response.text)
        self.assertIn("中央値 132,839円／年", response.text)
        self.assertIn("範囲 124,058円〜137,083円／年", response.text)
        self.assertNotIn("保存済みの将来THIデータはまだ画面へ接続しておらず", response.text)
        self.assertNotIn("将来の暑さに対する十分性は未評価です", response.text)

    def test_climate_costs_follow_user_plan_without_changing_it(self) -> None:
        response = TestClient(app).get(
            "/?lactating_cows=60&lane_count=2&existing_fan_count=10"
            "&first_phase_fan_count=3&planned_fan_count=18"
        )

        climate_section = re.search(
            r'<section class="climate-background".*?</section>',
            response.text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(climate_section)
        assert climate_section is not None
        self.assertIn("第1期：小さく始める（3台追加）", climate_section.group(0))
        self.assertIn("中央値 79,703円／年", climate_section.group(0))
        self.assertIn("今回の計画台数まで追加（8台追加）", response.text)

    def test_climate_costs_use_user_operating_hours_without_changing_thi_days(self) -> None:
        dashboard = _dashboard(
            60,
            2,
            10,
            None,
            2026,
            operating_hours_per_day=Decimal("12"),
        )

        climate = dashboard["climate_background"]
        near_future = climate["periods"][0]
        first_phase_cost = near_future["plans"][0]
        self.assertEqual(climate["operating_hours_per_day"], 12.0)
        self.assertAlmostEqual(near_future["central_lower_days"], 104.3166666667)
        self.assertAlmostEqual(near_future["central_upper_days"], 104.8166666667)
        self.assertEqual(first_phase_cost["additional_fan_count"], 5)
        self.assertEqual(first_phase_cost["annual_electricity_median_yen"], 82019)
        self.assertEqual(first_phase_cost["annual_electricity_minimum_yen"], 77629)
        self.assertEqual(first_phase_cost["annual_electricity_maximum_yen"], 84142)


if __name__ == "__main__":
    unittest.main()

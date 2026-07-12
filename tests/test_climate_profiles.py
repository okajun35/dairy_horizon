from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.climate_profiles import (
    ClimateProfileGenerationError,
    DEFAULT_MODELS,
    aggregate_daily_values,
    build_future_profile,
    daily_mean_thi,
)
from app.main import app
from app.vertical_slice import build_dashboard


ROOT = Path(__file__).resolve().parents[1]
CLIENT = TestClient(app)


def payload_for_model(model: str, _: str) -> dict:
    index = DEFAULT_MODELS.index(model)
    return {
        "latitude": 35.6074,
        "longitude": 140.1065,
        "daily_units": {"temperature_2m_mean": "°C", "temperature_2m_max": "°C"},
        "daily": {
            "time": ["2025-07-01", "2025-07-02", "2025-07-03", "2025-07-04", "2025-07-05"],
            "temperature_2m_mean": [20, 25, 25, 25, 20],
            "temperature_2m_max": [29, 30 + index, 31, 32, 29],
            "relative_humidity_2m_mean": [70, 70, 70, 70, 70],
            "wind_speed_10m_mean": [3, 3, 3, 3, 3],
        },
    }


class ClimateProfileTest(unittest.TestCase):
    def test_daily_mean_thi_and_yearly_aggregation(self) -> None:
        self.assertGreaterEqual(daily_mean_thi(25, 70), 72)
        result = aggregate_daily_values(payload_for_model(DEFAULT_MODELS[0], "")["daily"])[2025]
        self.assertEqual(3, result["hot_days_temperature_max_ge_30"])
        self.assertEqual(3, result["thi_days_daily_mean_ge_72"])
        self.assertEqual(3, result["max_consecutive_thi_days"])
        self.assertEqual(3.0, result["mean_outdoor_wind_speed_10m_mps"])

    def test_mocked_model_responses_produce_metadata_and_range_summary(self) -> None:
        profile = build_future_profile(
            region_id="test", region_name_ja="試験地域", latitude=35.0, longitude=140.0,
            start_year=2025, end_year=2025, fetch_model=payload_for_model,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        self.assertEqual("climate_model_projection_scenario", profile["classification"])
        self.assertEqual(7, len(profile["retrievals"]))
        self.assertTrue(all(item["status"] == "success" for item in profile["retrievals"]))
        year = profile["years"]["2025"]
        self.assertEqual(7, len(year["model_values"]))
        self.assertEqual(3, year["summary"]["thi_days_daily_mean_ge_72"]["median"])
        self.assertIn("outdoor_wind_note_ja", profile["aggregation_rules"])
        self.assertEqual("official_projection_report", profile["source"]["provenance_kind"])

    def test_fewer_than_four_models_fails_without_writing_a_profile(self) -> None:
        with self.assertRaisesRegex(ClimateProfileGenerationError, "at least four"):
            build_future_profile(
                region_id="test", region_name_ja="試験地域", latitude=35.0, longitude=140.0,
                start_year=2025, end_year=2025, fetch_model=payload_for_model,
                models=DEFAULT_MODELS[:3],
            )

    def test_one_missing_model_is_recorded_when_six_models_remain(self) -> None:
        def fetch_with_one_failure(model: str, url: str) -> dict:
            if model == "NICAM16_8S":
                raise OSError("temporary API failure")
            return payload_for_model(model, url)

        profile = build_future_profile(
            region_id="test", region_name_ja="試験地域", latitude=35.0, longitude=140.0,
            start_year=2025, end_year=2025, fetch_model=fetch_with_one_failure,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        failed = [item for item in profile["retrievals"] if item["status"] == "failed"]
        self.assertEqual(["NICAM16_8S"], [item["model"] for item in failed])
        self.assertEqual(6, len(profile["years"]["2025"]["model_values"]))

    def test_generated_chiba_profile_has_each_year_and_usable_model_metadata(self) -> None:
        path = ROOT / "data/climate_profiles/generated/chiba_city_2025_2034.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("climate_model_projection_scenario", profile["classification"])
        self.assertEqual(7, len(profile["retrievals"]))
        self.assertEqual({str(year) for year in range(2025, 2035)}, set(profile["years"]))
        self.assertTrue(all(len(item["model_values"]) >= 4 for item in profile["years"].values()))
        self.assertTrue(all("retrieved_at" in item for item in profile["retrievals"]))

    def test_future_year_changes_heat_days_and_economic_result(self) -> None:
        near = build_dashboard({"climate_year": "2025"})
        far = build_dashboard({"climate_year": "2034"})
        self.assertNotEqual(
            near["heat_context"]["heat_stress_days_median"],
            far["heat_context"]["heat_stress_days_median"],
        )
        self.assertGreater(
            far["plans"]["full_installation"]["maximum_affordable_capex_yen"],
            near["plans"]["full_installation"]["maximum_affordable_capex_yen"],
        )

    def test_failed_plan_exposes_three_conditions_to_approach_feasibility(self) -> None:
        plan = build_dashboard({"climate_year": "2025"})["plans"]["full_installation"]
        conditions = plan["conditions_to_approach_feasibility"]
        self.assertIsNotNone(conditions)
        self.assertIn("required_installed_cost_yen_per_unit", conditions)
        self.assertIn("required_avoided_milk_loss_kg_per_cow_day", conditions)
        self.assertIn("required_milk_price_yen_per_kg", conditions)

    def test_web_shows_projection_timeline_and_investment_timing_controls(self) -> None:
        response = CLIENT.get("/")
        self.assertEqual(200, response.status_code)
        self.assertIn("2026〜2034年の見通し", response.text)
        self.assertIn("気候モデルのシナリオ", response.text)
        self.assertIn('name="stage_one_year"', response.text)
        self.assertIn('name="annual_cash_before_heat_yen"', response.text)
        self.assertIn('value="1600000"', response.text)
        self.assertIn('name="maximum_debt_yen"', response.text)
        self.assertIn('id="timeline-chart"', response.text)
        response = CLIENT.post(
            "/",
            data={
                "lactating_cows": "60", "lane_count": "2", "existing_fan_count": "10",
                "milk_price_yen_per_kg": "170", "variable_cost_ratio_pct": "60",
                "avoided_milk_loss_kg_per_cow_day": "3", "electricity_price_yen_per_kwh": "27",
                "installed_cost_yen_per_unit": "220000", "evaluation_period_years": "5",
                "climate_year": "2034", "stage_one_year": "2028", "full_installation_year": "2029",
                "milk_price_change_yen_per_kg_per_year": "0", "electricity_price_change_pct_per_year": "0",
                "selected_plan": "full_installation",
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertIn("2028年 第1期 → 2029年 全数整備", response.text)


if __name__ == "__main__":
    unittest.main()

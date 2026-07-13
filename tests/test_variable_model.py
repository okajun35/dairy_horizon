from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.vertical_slice import (
    EconomicsInputs,
    InputValidationError,
    calculate_economics,
    calculate_required_fans,
    build_dashboard,
)

ROOT = Path(__file__).resolve().parents[1]
CLIENT = TestClient(app)


class VariableModelTest(unittest.TestCase):
    def run_layout(self, cows: int, rows: int, existing: int):
        scenario = {
            "barn_input": {
                "lactating_cows": cows,
                "row_count": rows,
                "existing_fan_count": existing,
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scenario_path = temp_path / "scenario.json"
            output_path = temp_path / "layout.json"
            scenario_path.write_text(
                json.dumps(scenario),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/generate_barn_layout.py"),
                    str(scenario_path),
                    str(output_path),
                ],
                check=True,
            )
            return json.loads(output_path.read_text(encoding="utf-8"))

    def test_60_cows_two_rows_requires_20_fans(self) -> None:
        result = self.run_layout(60, 2, 10)
        self.assertEqual([30, 30], result["derived"]["cows_per_row"])
        self.assertEqual(20, result["derived"]["target_fan_count"])
        self.assertEqual(10, result["derived"]["additional_fan_count"])

    def test_75_cows_two_rows_requires_26_fans(self) -> None:
        result = self.run_layout(75, 2, 12)
        self.assertEqual([38, 37], result["derived"]["cows_per_row"])
        self.assertEqual(26, result["derived"]["target_fan_count"])
        self.assertEqual(14, result["derived"]["additional_fan_count"])

    def test_zero_milk_price_returns_non_calculable_status(self) -> None:
        scenario = json.loads(
            (ROOT / "scenarios/chiba_60_cow_demo.json").read_text(
                encoding="utf-8"
            )
        )
        scenario["financial_input"]["base_milk_price_yen_per_kg"] = 0
        scenario["financial_input"]["milk_price_change_yen_per_kg"] = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scenario_path = temp_path / "scenario.json"
            output_path = temp_path / "result.json"
            scenario_path.write_text(
                json.dumps(scenario),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(
                        ROOT
                        / "scripts/calculate_zenrakuren_break_even.py"
                    ),
                    str(scenario_path),
                    str(output_path),
                ],
                check=True,
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                "recovery_impossible_at_zero_price",
                result["status"],
            )
            self.assertIsNone(
                result["result"]["break_even_milk_kg_per_cow_day"]
            )

    def test_higher_milk_price_lowers_break_even_volume(self) -> None:
        base_scenario = json.loads(
            (ROOT / "scenarios/chiba_60_cow_demo.json").read_text(
                encoding="utf-8"
            )
        )

        def calculate_at(price: float) -> float:
            scenario = json.loads(json.dumps(base_scenario))
            scenario["financial_input"][
                "base_milk_price_yen_per_kg"
            ] = price
            scenario["financial_input"][
                "milk_price_change_yen_per_kg"
            ] = 0
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                scenario_path = temp_path / "scenario.json"
                output_path = temp_path / "result.json"
                scenario_path.write_text(
                    json.dumps(scenario),
                    encoding="utf-8",
                )
                subprocess.run(
                    [
                        sys.executable,
                        str(
                            ROOT
                            / "scripts/calculate_zenrakuren_break_even.py"
                        ),
                        str(scenario_path),
                        str(output_path),
                    ],
                    check=True,
                )
                result = json.loads(
                    output_path.read_text(encoding="utf-8")
                )
                return result["result"][
                    "break_even_milk_kg_per_cow_day"
                ]

        self.assertGreater(calculate_at(100), calculate_at(150))

    def test_standard_example_reproduces_zenrakuren_break_even(self) -> None:
        result = calculate_economics(
            EconomicsInputs(
                incremental_fan_count=1,
                newly_covered_cow_count=3,
                installed_cost_yen_per_unit=Decimal("220000"),
                power_kw_per_unit=Decimal("0.4"),
                operating_hours_per_day=Decimal("24"),
                heat_stress_days_per_year=Decimal("120"),
                electricity_price_yen_per_kwh=Decimal("27"),
                basic_charge_yen_per_kw_month=Decimal("1300"),
                inverter_reduction_ratio=Decimal("0.25"),
                useful_life_years=7,
                evaluation_period_years=7,
                milk_price_yen_per_kg=Decimal("135"),
                variable_cost_ratio=Decimal("0.60"),
                avoided_milk_loss_kg_per_cow_day=Decimal("4"),
            )
        )
        self.assertAlmostEqual(
            float(result["break_even_milk_yield_kg_per_cow_day"]),
            3.1377,
            places=4,
        )

    def test_stage_one_and_full_incremental_costs(self) -> None:
        dashboard = build_dashboard()
        stage = dashboard["plans"]["stage_1"]
        full = dashboard["plans"]["full_installation"]
        self.assertEqual(5, stage["incremental_fan_count"])
        self.assertEqual(10, full["incremental_fan_count"])
        self.assertEqual(15, stage["newly_covered_cow_count"])
        self.assertEqual(30, full["newly_covered_cow_count"])
        self.assertEqual(Decimal("1100000"), stage["incremental_capex_yen"])
        self.assertEqual(Decimal("2200000"), full["incremental_capex_yen"])

    def test_evaluation_period_changes_simple_payback(self) -> None:
        dashboard = build_dashboard()
        five_year = dashboard["plans"]["full_installation"]
        seven_year = build_dashboard({"evaluation_period_years": "7"})["plans"]["full_installation"]
        self.assertGreater(
            five_year["break_even_milk_yield_kg_per_cow_day"],
            seven_year["break_even_milk_yield_kg_per_cow_day"],
        )
        self.assertLess(
            five_year["maximum_affordable_capex_yen"],
            seven_year["maximum_affordable_capex_yen"],
        )

    def test_zero_milk_price_is_safe_in_dashboard(self) -> None:
        plan = build_dashboard({"milk_price_yen_per_kg": "0"})["plans"]["full_installation"]
        self.assertEqual("recovery_impossible", plan["break_even_status"])
        self.assertEqual("zero_milk_price", plan["break_even_reason"])
        self.assertEqual(Decimal("0"), plan["maximum_affordable_capex_yen"])
        self.assertFalse(plan["preserves_requested_window"])

    def test_higher_milk_price_does_not_reduce_affordable_capex(self) -> None:
        low = build_dashboard({"milk_price_yen_per_kg": "120"})["plans"]["full_installation"]
        high = build_dashboard({"milk_price_yen_per_kg": "150"})["plans"]["full_installation"]
        self.assertLessEqual(low["maximum_affordable_capex_yen"], high["maximum_affordable_capex_yen"])

    def test_variable_cost_ratio_is_editable_but_limited_to_95_percent(self) -> None:
        dashboard = build_dashboard({"variable_cost_ratio_pct": "65"})
        self.assertEqual("65", dashboard["values"]["variable_cost_ratio_pct"])
        with self.assertRaises(InputValidationError):
            build_dashboard({"variable_cost_ratio_pct": "95.1"})

    def test_same_input_returns_same_result(self) -> None:
        one = build_dashboard({"lactating_cows": "75", "existing_fan_count": "12"})
        two = build_dashboard({"lactating_cows": "75", "existing_fan_count": "12"})
        self.assertEqual(one["plans"], two["plans"])

    def test_no_additional_investment_required(self) -> None:
        dashboard = build_dashboard({"existing_fan_count": "20"})
        plan = dashboard["plans"]["full_installation"]
        self.assertEqual("no_additional_investment_required", plan["plan_status"])
        self.assertEqual(0, plan["incremental_fan_count"])
        self.assertEqual([], plan["newly_covered_cow_ids"])

    def test_uneven_rows_are_deterministic(self) -> None:
        cows, fans = calculate_required_fans(75, 2, 3)
        self.assertEqual([38, 37], cows)
        self.assertEqual([13, 13], fans)

    def test_stage_one_uses_leftmost_missing_slots(self) -> None:
        dashboard = build_dashboard()
        selected = [
            fan for fan in dashboard["layout"]["fans"]
            if fan["stage_one_selected"]
        ]
        self.assertEqual(
            [(1, 0), (1, 2), (1, 4), (2, 0), (2, 2)],
            [(fan["lane_id"], fan["slot_index"]) for fan in selected],
        )

    def test_period_beyond_life_keeps_reference_values_but_fails(self) -> None:
        plan = build_dashboard({"evaluation_period_years": "8"})["plans"]["full_installation"]
        self.assertEqual("calculable", plan["break_even_status"])
        self.assertIsNotNone(plan["maximum_affordable_capex_yen"])
        self.assertFalse(plan["preserves_requested_window"])
        self.assertEqual("evaluation_period_exceeds_useful_life", plan["first_failing_condition"])

    def test_web_initial_display_and_recalculation(self) -> None:
        response = CLIENT.get("/")
        self.assertEqual(200, response.status_code)
        self.assertIn("30秒試算", response.text)
        self.assertIn("詳細試算", response.text)

        response = CLIENT.post(
            "/",
            data={
                "lactating_cows": "75",
                "lane_count": "2",
                "existing_fan_count": "12",
                "milk_price_yen_per_kg": "135",
                "variable_cost_ratio_pct": "60",
                "avoided_milk_loss_kg_per_cow_day": "3",
                "electricity_price_yen_per_kwh": "27",
                "installed_cost_yen_per_unit": "220000",
                "evaluation_period_years": "5",
                "target_years": "5",
                "selected_plan": "full_installation",
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertIn("設定した5年間を守れる可能性", response.text)

    def test_zero_milk_price_post_is_recovery_impossible(self) -> None:
        response = CLIENT.post(
            "/",
            data={
                "lactating_cows": "60",
                "lane_count": "2",
                "existing_fan_count": "10",
                "milk_price_yen_per_kg": "0",
                "variable_cost_ratio_pct": "60",
                "avoided_milk_loss_kg_per_cow_day": "3",
                "electricity_price_yen_per_kwh": "27",
                "installed_cost_yen_per_unit": "220000",
                "evaluation_period_years": "5",
                "selected_plan": "full_installation",
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertIn("乳価が未入力のため、回収の見込みを判断できません", response.text)

    def test_quote_request_contains_required_details(self) -> None:
        quote = build_dashboard()["quote_request"]
        self.assertIn("搾乳牛 60 頭", quote)
        self.assertIn("追加ファン台数", quote)
        self.assertIn("目標風速2m/s", quote)
        self.assertIn("税込・税抜", quote)


if __name__ == "__main__":
    unittest.main()

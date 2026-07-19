from __future__ import annotations

from decimal import Decimal
import unittest

from fastapi.testclient import TestClient

from app.financial_screening import FinancialPlan, STANDARD_FINANCIAL_ASSUMPTIONS
from app.future_outlook import build_future_outlook
from app.main import app


class FutureOutlookTest(unittest.TestCase):
    def test_builds_four_controls_anchored_at_each_break_even(self) -> None:
        result = build_future_outlook(
            first_phase_plan=FinancialPlan(5, 15),
            full_additional_fan_count=10,
            assumptions=STANDARD_FINANCIAL_ASSUMPTIONS,
        )

        self.assertEqual(result.first_phase_additional_fan_count, 5)
        self.assertEqual(result.second_phase_candidate_fan_count, 5)
        self.assertEqual(
            [control.key for control in result.controls],
            [
                "avoided_milk_loss_kg_per_cow_day",
                "milk_price_yen_per_kg",
                "electricity_price_yen_per_kwh",
                "operating_hours_per_day",
            ],
        )
        for control in result.controls:
            self.assertEqual(control.status, "reachable")
            self.assertIsNotNone(control.break_even_value)
            break_even_point = next(point for point in control.points if point.is_break_even)
            self.assertEqual(break_even_point.annual_project_balance_yen, Decimal("0"))
            self.assertGreater(len(control.points), 3)

    def test_marks_a_condition_without_a_zero_crossing_as_unreachable(self) -> None:
        result = build_future_outlook(
            first_phase_plan=FinancialPlan(5, 15),
            full_additional_fan_count=10,
            assumptions=STANDARD_FINANCIAL_ASSUMPTIONS.__class__(
                **{
                    **STANDARD_FINANCIAL_ASSUMPTIONS.__dict__,
                    "avoided_milk_loss_kg_per_cow_day": Decimal("0"),
                }
            ),
        )

        milk_price = next(
            control for control in result.controls if control.key == "milk_price_yen_per_kg"
        )
        self.assertEqual(milk_price.status, "always_negative")
        self.assertIsNone(milk_price.break_even_value)

    def test_screen_shows_full_coverage_comparison_without_a_second_phase(self) -> None:
        response = TestClient(app).get(
            "/check?future_target_cow_count=45&confirmed_covered_cow_count=12"
        )

        self.assertIn('id="future-outlook"', response.text)
        self.assertIn("全体を整えた場合", response.text)
        self.assertIn("さらに+5台", response.text)
        self.assertNotIn("第2期候補", response.text)
        self.assertIn("回収ライン", response.text)
        self.assertIn("暑い日に防げた乳量低下", response.text)
        self.assertIn("実現乳価", response.text)
        self.assertIn("電力量単価", response.text)
        self.assertIn("暑い日の運転時間", response.text)
        self.assertIn("4条件を合わせた第1期の年間差引", response.text)
        self.assertIn("回収ライン（損得0円の境目）", response.text)
        self.assertIn("いまの値：<strong data-outlook-value></strong>", response.text)
        self.assertIn('data-outlook-unit="kg／頭・暑熱日"', response.text)
        self.assertIn("スライダーは結果を保存・変更しません", response.text)
        self.assertNotIn('data-primary-input="avoided_milk_loss_kg_per_cow_day"', response.text)

    def test_aggregate_balance_endpoint_uses_the_python_annual_calculation(self) -> None:
        client = TestClient(app)
        negative = client.get(
            "/future-outlook/balance",
            params={
                "additional_fan_count": 5,
                "covered_cow_count": 15,
                "avoided_milk_loss_kg_per_cow_day": "0",
                "milk_price_yen_per_kg": "135",
                "electricity_price_yen_per_kwh": "27",
                "operating_hours_per_day": "24",
            },
        )
        positive = client.get(
            "/future-outlook/balance",
            params={
                "additional_fan_count": 5,
                "covered_cow_count": 15,
                "avoided_milk_loss_kg_per_cow_day": "10",
                "milk_price_yen_per_kg": "135",
                "electricity_price_yen_per_kwh": "27",
                "operating_hours_per_day": "24",
            },
        )

        self.assertEqual(negative.status_code, 200)
        self.assertEqual(positive.status_code, 200)
        self.assertLess(Decimal(negative.json()["balance_yen"]), Decimal("0"))
        self.assertGreater(Decimal(positive.json()["balance_yen"]), Decimal("0"))

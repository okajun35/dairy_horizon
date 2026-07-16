from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from app.main import app


def _first_phase_card(response_text: str) -> str:
    match = re.search(
        r'<article class="financial-plan-card" data-financial-plan="first_phase">(.*?)</article>',
        response_text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("first phase financial card was not rendered")
    return match.group(1)


class FinancialAssumptionInputTest(unittest.TestCase):
    def test_realized_milk_price_recalculates_required_milk(self) -> None:
        response = TestClient(app).get(
            "/check?milk_price_yen_per_kg=150"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("2.82kg／頭・日", _first_phase_card(response.text))
        self.assertIn("実現乳価</dt><dd>150円／kg", response.text)
        self.assertIn("実現乳価", response.text)

    def test_electricity_price_recalculates_every_electricity_view(self) -> None:
        response = TestClient(app).get(
            "/check?future_target_cow_count=45&electricity_price_yen_per_kwh=30"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("160,800円", _first_phase_card(response.text))
        self.assertIn("電力量単価</dt><dd>30円／kWh", response.text)
        self.assertIn("136,230円／年", response.text)
        self.assertIn("144,960円／年", response.text)

    def test_summer_milk_difference_replaces_demo_benefit_assumption(self) -> None:
        response = TestClient(app).get(
            "/check?avoided_milk_loss_kg_per_cow_day=2.5"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("夏季の防止乳量差</dt><dd>2.5kg／頭・日", response.text)
        self.assertIn("666,120円", response.text)
        self.assertIn("夏季の防止乳量差", response.text)

    def test_invalid_financial_input_returns_safe_japanese_error(self) -> None:
        response = TestClient(app).get(
            "/check?milk_price_yen_per_kg=not-a-number"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("実現乳価は0以上の数値で入力してください", response.text)
        self.assertNotIn("InvalidOperation", response.text)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from app.main import app


def _annual_balance(response_text: str) -> str:
    match = re.search(r"年間の差引</dt><dd[^>]*>([^<]+)</dd>", response_text)
    if match is None:
        raise AssertionError("annual project balance was not rendered")
    return match.group(1)


class FarmSalesContextViewTest(unittest.TestCase):
    def test_direct_shipments_show_sales_scale_without_changing_project_balance(self) -> None:
        base_params = {
            "future_target_cow_count": 45,
            "confirmed_covered_cow_count": 15,
            "avoided_milk_loss_kg_per_cow_day": 3,
            "milk_price_yen_per_kg": 150,
        }
        client = TestClient(app)
        without_shipments = client.get("/check", params=base_params)
        with_shipments = client.get(
            "/check",
            params=base_params
            | {
                "current_annual_shipped_milk_kg": 600000,
                "future_annual_shipped_milk_kg": 450000,
            },
        )

        self.assertEqual(with_shipments.status_code, 200)
        self.assertIn("売上規模の背景", with_shipments.text)
        self.assertIn("現在の年間出荷乳量", with_shipments.text)
        self.assertIn("600,000kg／年", with_shipments.text)
        self.assertIn("現在の年間乳代売上", with_shipments.text)
        self.assertIn("90,000,000円", with_shipments.text)
        self.assertIn("5年後の年間出荷乳量", with_shipments.text)
        self.assertIn("450,000kg／年", with_shipments.text)
        self.assertIn("67,500,000円", with_shipments.text)
        self.assertIn("採算判定には使用しません", with_shipments.text)
        self.assertIn("365日", with_shipments.text)
        self.assertEqual(
            _annual_balance(with_shipments.text),
            _annual_balance(without_shipments.text),
        )

    def test_future_sales_is_not_inferred_from_future_cow_count(self) -> None:
        response = TestClient(app).get(
            "/check?future_target_cow_count=45"
            "&current_annual_shipped_milk_kg=600000"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("5年後の年間乳代売上</dt><dd>未評価", response.text)


if __name__ == "__main__":
    unittest.main()

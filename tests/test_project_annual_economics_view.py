from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app


class ProjectAnnualEconomicsViewTest(unittest.TestCase):
    def test_current_and_future_snapshots_show_the_full_annual_bridge(self) -> None:
        response = TestClient(app).get(
            "/check?future_target_cow_count=45"
            "&confirmed_covered_cow_count=15"
            "&avoided_milk_loss_kg_per_cow_day=3"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("対策単体の年間収支", response.text)
        self.assertIn("年間防止乳量", response.text)
        self.assertIn("4,376kg", response.text)
        self.assertIn("4,740kg", response.text)
        self.assertIn("年間限界利益効果", response.text)
        self.assertIn("236,318円", response.text)
        self.assertIn("255,960円", response.text)
        self.assertIn("設備の年間負担", response.text)
        self.assertIn("282,870円", response.text)
        self.assertIn("290,727円", response.text)
        self.assertIn("年間の差引", response.text)
        self.assertIn("-46,552円", response.text)
        self.assertIn("-34,767円", response.text)
        self.assertIn("annual-balance-negative", response.text)
        self.assertIn("入力した値", response.text)
        self.assertIn("農場全体のキャッシュフローではありません", response.text)


if __name__ == "__main__":
    unittest.main()

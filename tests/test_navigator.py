from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.navigator import BarnInput, build_navigation


class NavigatorTest(unittest.TestCase):
    def test_60_cows_has_20_required_fans_and_10_fan_gap(self) -> None:
        result = build_navigation(BarnInput(60, 2, 10))
        self.assertEqual(result.required_fans_by_lane, (10, 10))
        self.assertEqual(result.shortage_fan_count, 10)
        self.assertEqual(len(result.plans[0].covered_cow_ids), 30)
        self.assertEqual(result.plans[1].additional_fan_count, 5)
        self.assertEqual(len(result.plans[1].newly_covered_cow_ids), 15)

    def test_75_cows_are_split_deterministically(self) -> None:
        result = build_navigation(BarnInput(75, 2, 12))
        self.assertEqual(tuple(len(lane) for lane in result.cows_by_lane), (38, 37))
        self.assertEqual(result.required_fan_count, 26)

    def test_no_extra_fans_is_not_an_investment_success(self) -> None:
        result = build_navigation(BarnInput(60, 2, 20))
        self.assertTrue(all(plan.status == "NOT_REQUIRED" for plan in result.plans))
        self.assertTrue(all(plan.additional_fan_count == 0 for plan in result.plans))

    def test_screen_contains_barn_and_evidence(self) -> None:
        response = TestClient(app).get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="barn-viewer"', response.text)
        self.assertIn("標準仮定・計算根拠", response.text)
        self.assertIn("将来気候から投資年や必要台数は決めません", response.text)
        self.assertNotIn("見積依頼文", response.text)


if __name__ == "__main__":
    unittest.main()

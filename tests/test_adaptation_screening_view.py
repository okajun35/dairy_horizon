from __future__ import annotations

from html import unescape
import json
import re
import unittest

from fastapi.testclient import TestClient

from app.main import app, get_natural_input_interpreter
from app.natural_input import NaturalInputCandidate


def _viewer_payload(response_text: str) -> dict[str, object]:
    match = re.search(
        r'<script id="barn-payload" type="application/json">(.*?)</script>',
        response_text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("barn payload was not rendered")
    return json.loads(unescape(match.group(1)))


class AdaptationScreeningViewTest(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_reduction_demo_separates_current_future_and_transition(self) -> None:
        response = TestClient(app).get(
            "/check",
            params={
                "lactating_cows": 60,
                "lane_count": 2,
                "existing_fan_count": 10,
                "first_phase_fan_count": 5,
                "future_target_cow_count": 45,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("現在・追加前", response.text)
        self.assertIn("60頭", response.text)
        self.assertIn("10台不足", response.text)
        self.assertIn("現在・第1期後", response.text)
        self.assertIn("5台不足", response.text)
        self.assertIn("5年後・第1期後", response.text)
        self.assertIn("45頭", response.text)
        self.assertIn("頭数基準上は不足なし", response.text)
        self.assertIn("移行期間中は頭数基準上の不足が残ります", response.text)
        self.assertIn("実際の送風範囲は未確認", response.text)
        self.assertIn("現在条件での年間回収目安", response.text)
        self.assertIn("5年後条件での年間回収目安", response.text)
        self.assertIn("97.3日／年", response.text)
        self.assertIn("105.3日／年", response.text)
        self.assertIn("125,727円／年", response.text)
        self.assertIn("133,584円／年", response.text)
        self.assertIn("3.59kg／頭・日", response.text)
        self.assertIn("3.41kg／頭・日", response.text)
        self.assertIn("5年間の累積ROIではありません", response.text)
        self.assertIn('name="future_target_cow_count"', response.text)
        self.assertIn('value="45"', response.text)
        payload = _viewer_payload(response.text)
        adaptation = payload["two_horizon_screening"]
        self.assertEqual(adaptation["future_after"]["target_cow_count"], 45)

    def test_confirmed_coverage_recalculates_first_phase_finance(self) -> None:
        response = TestClient(app).get(
            "/check",
            params={
                "lactating_cows": 60,
                "lane_count": 2,
                "existing_fan_count": 10,
                "first_phase_fan_count": 5,
                "future_target_cow_count": 45,
                "confirmed_covered_cow_count": 12,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("実測で確認した12頭を回収計算へ反映", response.text)
        self.assertIn("3.92kg／頭・日", response.text)
        self.assertIn("4.49kg／頭・日", response.text)
        self.assertIn("4.26kg／頭・日", response.text)
        self.assertIn("次に確認する情報は、夏季の乳量差です", response.text)

    def test_missing_future_count_is_shown_as_the_next_branch(self) -> None:
        response = TestClient(app).get(
            "/check?lactating_cows=60&lane_count=2&existing_fan_count=10"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("5年後の対策対象頭数を入力すると", response.text)
        self.assertIn("次に確認する情報は、5年後の対策対象頭数です", response.text)

    def test_three_equipment_types_show_one_complete_path_and_two_measurement_branches(self) -> None:
        response = TestClient(app).get(
            "/check?lactating_cows=60&lane_count=2&existing_fan_count=10&future_target_cow_count=45"
        )

        self.assertIn("標準100cm級", response.text)
        self.assertIn("省電力100cm級", response.text)
        self.assertIn("大型高風量型", response.text)
        self.assertIn("92,400円", response.text)
        self.assertIn("155,971円", response.text)
        self.assertIn("必要台数とカバー範囲は未評価", response.text)
        self.assertNotIn("needs_measurement", response.text)

    def test_natural_input_preserves_extracted_future_count_for_confirmation(self) -> None:
        class FakeInterpreter:
            def interpret(self, _text: str) -> NaturalInputCandidate:
                return NaturalInputCandidate(
                    "千葉市", 60, 2, 10, (), future_target_cow_count=45
                )

        app.dependency_overrides[get_natural_input_interpreter] = lambda: FakeInterpreter()
        response = TestClient(app).post(
            "/interpret",
            data={"farm_description": "現在60頭、5年後45頭、2列、既存10台"},
        )

        self.assertIn(
            'name="future_target_cow_count" type="hidden" value="45"',
            response.text,
        )
        self.assertIn("5年後45頭を読み取り", response.text)


if __name__ == "__main__":
    unittest.main()

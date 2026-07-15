from __future__ import annotations

from html import unescape
import json
import re
import unittest

from fastapi.testclient import TestClient

from app.main import app, get_natural_input_interpreter
from app.natural_input import NaturalInputCandidate


def _payload(response_text: str) -> dict[str, object]:
    match = re.search(
        r'<script id="barn-payload" type="application/json">(.*?)</script>',
        response_text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("barn payload was not rendered")
    return json.loads(unescape(match.group(1)))


class ReferenceInputTest(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_missing_region_and_existing_fans_offer_a_transparent_reference_state(self) -> None:
        class FakeInterpreter:
            def interpret(self, _text: str) -> NaturalInputCandidate:
                return NaturalInputCandidate(
                    None,
                    100,
                    4,
                    None,
                    ("region_ja", "existing_fan_count"),
                )

        app.dependency_overrides[get_natural_input_interpreter] = lambda: FakeInterpreter()

        response = TestClient(app).post(
            "/interpret",
            data={"farm_description": "牛を100頭飼っていて牛舎は4列です"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('value="千葉市" disabled aria-describedby="candidate-region-availability-note"', response.text)
        self.assertIn('name="region_ja" type="hidden" value="千葉市"', response.text)
        self.assertIn("現在の対応地域として設定", response.text)
        self.assertIn('name="lactating_cows" type="number" min="1" max="300" value="100"', response.text)
        self.assertIn('name="lane_count" type="number" min="1" max="6" value="4"', response.text)
        self.assertIn('name="existing_fan_count" type="number" min="0" value=""', response.text)
        self.assertIn("現在使っているファンは何台ですか？", response.text)
        self.assertIn("34台の参考状態を見る", response.text)
        self.assertIn('name="reference_mode" type="hidden" value="true"', response.text)
        self.assertNotIn("user_input_candidate", response.text)

    def test_reference_state_prefills_and_evaluates_the_guideline_count(self) -> None:
        response = TestClient(app).get(
            "/",
            params={
                "region_ja": "千葉市",
                "lactating_cows": 100,
                "lane_count": 4,
                "existing_fan_count": 34,
                "reference_mode": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = _payload(response.text)
        self.assertEqual(payload["input_mode"], "guideline_reference")
        self.assertIn("頭数基準の参考状態", response.text)
        self.assertIn("現在のファン数</dt><dd>未確認", response.text)
        self.assertIn("頭数基準の台数目安</dt><dd>34台", response.text)
        self.assertIn("参考配置</dt><dd>34台", response.text)
        self.assertIn("参考状態での不足</dt><dd>0台", response.text)
        self.assertIn("未カバー推計</dt><dd>0頭", response.text)
        self.assertIn('name="existing_fan_count" type="number" min="0" value="34"', response.text)
        self.assertIn("台数を増減して牛舎を更新できます", response.text)
        self.assertIn('id="comparison-barn-viewer"', response.text)
        self.assertIn("未カバー状態の延べ規模", response.text)
        self.assertIn("0 — 未カバーなし", response.text)
        self.assertIn(
            'data-comparison-barn-heading>追加投資がないため、参考状態と同じ牛舎',
            response.text,
        )
        self.assertIn(
            "将来の暑熱期間は、下の背景情報で運転日数と電力費へ分けて確認します",
            response.text,
        )
        self.assertNotIn("現在の不足</dt><dd>未評価", response.text)

    def test_adjusted_reference_count_remains_a_reference_and_is_recalculated(self) -> None:
        response = TestClient(app).get(
            "/",
            params={
                "region_ja": "千葉市",
                "lactating_cows": 100,
                "lane_count": 4,
                "existing_fan_count": 30,
                "reference_mode": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = _payload(response.text)
        self.assertEqual(payload["input_mode"], "guideline_reference")
        self.assertIn('name="existing_fan_count" type="number" min="0" value="30"', response.text)
        self.assertIn("参考配置</dt><dd>30台", response.text)
        self.assertIn("参考状態での不足</dt><dd>4台", response.text)
        self.assertIn("未カバー推計</dt><dd>10頭", response.text)
        self.assertIn('name="reference_mode" value="true"', response.text)
        self.assertIn("参考状態を更新", response.text)
        self.assertIn("実際の台数として計算", response.text)
        self.assertIn('id="comparison-barn-viewer"', response.text)
        self.assertIn("追加する台数</dt><dd data-selected-additional>+4台", response.text)
        self.assertIn("稼働ファン</dt><dd data-selected-active>34台", response.text)
        self.assertIn("新たにカバー推計</dt><dd data-selected-newly>+10頭", response.text)
        self.assertIn("未カバー推計</dt><dd data-selected-uncovered>0頭", response.text)
        self.assertIn('<input name="reference_mode" type="hidden" value="true">', response.text)

    def test_entering_actual_fan_count_switches_to_confirmed_current_state(self) -> None:
        response = TestClient(app).get(
            "/",
            params={
                "region_ja": "千葉市",
                "lactating_cows": 100,
                "lane_count": 4,
                "existing_fan_count": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = _payload(response.text)
        self.assertEqual(payload["input_mode"], "confirmed")
        self.assertIn("現在の不足", response.text)
        self.assertIn("頭数基準の台数目安</dt><dd>34台", response.text)
        self.assertIn("目安との差</dt><dd>24台", response.text)
        self.assertIn("未カバー推計</dt><dd>70頭", response.text)
        self.assertIn("年度別経路", response.text)

    def test_reference_comparison_keeps_current_first_phase_and_guideline_plans(self) -> None:
        response = TestClient(app).get(
            "/",
            params={
                "region_ja": "千葉市",
                "lactating_cows": 100,
                "lane_count": 4,
                "existing_fan_count": 20,
                "reference_mode": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = _payload(response.text)
        plans = payload["plans"]
        self.assertEqual(
            [
                (plan["key"], plan["additional_fan_count"], plan["active_fan_count"])
                for plan in plans
            ],
            [
                ("current", 0, 20),
                ("first_phase", 5, 25),
                ("full_coverage", 14, 34),
            ],
        )
        self.assertIn("第1期：小さく始める", response.text)
        self.assertIn("頭数目安まで追加", response.text)


if __name__ == "__main__":
    unittest.main()

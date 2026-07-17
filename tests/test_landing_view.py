from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from app.main import app


class LandingViewTest(unittest.TestCase):
    def test_landing_explains_the_product_before_starting_the_check(self) -> None:
        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("自分で判断するための指標をつくる", response.text)
        self.assertIn("現在相当（2020〜2025年）", response.text)
        self.assertIn("近未来（2026〜2030年）", response.text)
        self.assertIn("次の期間（2031〜2034年）", response.text)
        self.assertIn('href="/check?future_target_cow_count=45"', response.text)
        self.assertIn("まずモデルケースで始める", response.text)
        self.assertIn("現在60頭・2列・ファン10台・5年後45頭の入力例", response.text)
        self.assertNotIn("自分の牛舎で確認する", response.text)
        self.assertNotIn('id="current-barn-viewer"', response.text)

    def test_check_page_keeps_the_deterministic_barn_result(self) -> None:
        response = TestClient(app).get("/check")

        self.assertEqual(response.status_code, 200)
        self.assertIn("牛舎の条件を順番に整理する", response.text)
        self.assertIn('id="step-1"', response.text)
        self.assertIn('id="step-2"', response.text)
        self.assertIn('id="step-3"', response.text)
        self.assertIn('id="next-step"', response.text)
        self.assertIn('id="current-barn-viewer"', response.text)
        self.assertIn('id="comparison-current-barn-viewer"', response.text)
        self.assertIn('action="/check#step-2"', response.text)
        self.assertIn('class="climate-outlook"', response.text)
        self.assertIn("THI 72以上の日数が増える可能性があります", response.text)
        self.assertIn("10年後（2036年ごろ）", response.text)
        self.assertIn("2035年以降は外挿せず、取得済みデータがありません", response.text)

        step_2 = response.text.index('id="step-2"')
        current_barn = response.text.index('id="current-barn-viewer"')
        climate_outlook = response.text.index('class="climate-outlook"')
        step_3 = response.text.index('id="step-3"')
        comparison_current_barn = response.text.index(
            'id="comparison-current-barn-viewer"'
        )
        self.assertLess(step_2, current_barn)
        self.assertLess(climate_outlook, step_2)
        self.assertLess(current_barn, step_3)
        self.assertLess(step_3, comparison_current_barn)
        self.assertRegex(
            response.text,
            re.compile(
                r'牛床列数</dt><dd>2列</dd><small>下の牛舎図を2列で配置',
            ),
        )
        self.assertIn('class="result-support"', response.text)
        self.assertIn("まず見る要点", response.text)
        self.assertIn("<strong>第1期の機器分岐</strong>", response.text)
        self.assertIn("<strong>暑熱期間の背景</strong>", response.text)
        self.assertIn("<strong>標準条件での採算確認</strong>", response.text)


if __name__ == "__main__":
    unittest.main()

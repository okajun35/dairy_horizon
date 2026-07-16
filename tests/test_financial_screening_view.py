from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from app.main import app


def _financial_card(response_text: str, plan_key: str) -> str:
    match = re.search(
        rf'<article class="financial-plan-card" data-financial-plan="{plan_key}">(.*?)</article>',
        response_text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"financial card was not rendered: {plan_key}")
    return match.group(1)


class FinancialScreeningViewTest(unittest.TestCase):
    def test_standard_first_phase_and_guideline_plans_are_compared(self) -> None:
        response = TestClient(app).get("/check")

        self.assertEqual(response.status_code, 200)
        self.assertIn("追加案の費用と回収条件を比べる", response.text)

        first_phase = _financial_card(response.text, "first_phase")
        self.assertIn("第1期：小さく始める", first_phase)
        self.assertIn("追加台数</dt><dd>5台", first_phase)
        self.assertIn("新たにカバー推計</dt><dd>15頭", first_phase)
        self.assertIn("導入費</dt><dd>1,100,000円", first_phase)
        self.assertIn("年間電気代</dt><dd>147,840円", first_phase)
        self.assertIn("回収に必要な防止乳量</dt><dd>3.14kg／頭・日", first_phase)

        guideline = _financial_card(response.text, "full_coverage")
        self.assertIn("頭数目安まで追加", guideline)
        self.assertIn("追加台数</dt><dd>10台", guideline)
        self.assertIn("新たにカバー推計</dt><dd>30頭", guideline)
        self.assertIn("導入費</dt><dd>2,200,000円", guideline)
        self.assertIn("年間電気代</dt><dd>295,680円", guideline)
        self.assertIn("回収に必要な防止乳量</dt><dd>3.14kg／頭・日", guideline)

    def test_financial_cards_follow_user_changed_plan_counts(self) -> None:
        response = TestClient(app).get(
            "/check?lactating_cows=60&lane_count=2&existing_fan_count=10"
            "&first_phase_fan_count=3&planned_fan_count=18"
        )

        first_phase = _financial_card(response.text, "first_phase")
        self.assertIn("追加台数</dt><dd>3台", first_phase)
        self.assertIn("新たにカバー推計</dt><dd>9頭", first_phase)
        self.assertIn("導入費</dt><dd>660,000円", first_phase)
        self.assertIn("年間電気代</dt><dd>88,704円", first_phase)

        planned = _financial_card(response.text, "full_coverage")
        self.assertIn("今回の計画台数まで追加", planned)
        self.assertIn("追加台数</dt><dd>8台", planned)
        self.assertIn("新たにカバー推計</dt><dd>24頭", planned)
        self.assertIn("導入費</dt><dd>1,760,000円", planned)
        self.assertIn("年間電気代</dt><dd>236,544円", planned)

    def test_user_operating_hours_update_cost_and_recovery_but_not_capex(self) -> None:
        response = TestClient(app).get("/check?operating_hours_per_day=12")

        self.assertEqual(response.status_code, 200)
        first_phase = _financial_card(response.text, "first_phase")
        self.assertIn("導入費</dt><dd>1,100,000円", first_phase)
        self.assertIn("年間電気代</dt><dd>89,520円", first_phase)
        self.assertIn("回収に必要な防止乳量</dt><dd>2.54kg／頭・日", first_phase)
        self.assertIn("暑い日の平均運転時間", response.text)
        self.assertIn('name="operating_hours_per_day"', response.text)
        self.assertIn('value="12"', response.text)
        self.assertIn("暑い日の平均運転時間</dt><dd>12時間／日", response.text)
        self.assertIn("標準の暑熱対策日数</dt><dd>120日／年", response.text)
        self.assertIn("利用者入力", response.text)

    def test_invalid_operating_hours_use_safe_error_and_standard_fallback(self) -> None:
        response = TestClient(app).get("/check?operating_hours_per_day=25")

        self.assertEqual(response.status_code, 200)
        self.assertIn("運転時間は0〜24時間で入力してください", response.text)
        self.assertIn('name="operating_hours_per_day"', response.text)
        self.assertIn('value="24"', response.text)

    def test_zero_operating_hours_keeps_basic_charge_and_hides_recovery_claim(self) -> None:
        response = TestClient(app).get("/check?operating_hours_per_day=0")

        first_phase = _financial_card(response.text, "first_phase")
        self.assertIn("年間電気代</dt><dd>31,200円", first_phase)
        self.assertIn("回収に必要な防止乳量</dt><dd>評価対象外", first_phase)
        self.assertIn("基本料金だけを表示し、回収条件は計算しません", first_phase)

    def test_no_investment_uses_safe_japanese_display(self) -> None:
        response = TestClient(app).get(
            "/check?lactating_cows=60&lane_count=2&existing_fan_count=20"
        )

        for plan_key in ("first_phase", "full_coverage"):
            card = _financial_card(response.text, plan_key)
            self.assertIn("追加台数</dt><dd>0台", card)
            self.assertIn("導入費</dt><dd>0円", card)
            self.assertIn("年間電気代</dt><dd>0円", card)
            self.assertIn("回収に必要な防止乳量</dt><dd>評価対象外", card)
        self.assertNotIn("not_applicable", response.text)
        self.assertNotIn("no_investment", response.text)

    def test_standard_assumptions_and_reference_limit_are_explicit(self) -> None:
        response = TestClient(app).get(
            "/check?lactating_cows=100&lane_count=4&existing_fan_count=20&reference_mode=true"
        )

        self.assertIn("参考状態から追加する場合の標準試算", response.text)
        self.assertIn("実際の既存台数を確認すると結果が変わります", response.text)
        self.assertIn("1台あたり設備費</dt><dd>220,000円", response.text)
        self.assertIn("暑い日の平均運転時間</dt><dd>24時間／日", response.text)
        self.assertIn("標準の暑熱対策日数</dt><dd>120日／年", response.text)
        self.assertIn("電力量単価</dt><dd>27円／kWh", response.text)
        self.assertIn("インバーター削減率</dt><dd>25%", response.text)
        self.assertIn("法定耐用年数</dt><dd>7年", response.text)
        self.assertIn("変動費率</dt><dd>60%", response.text)
        self.assertIn("実現乳価</dt><dd>135円／kg", response.text)
        self.assertIn("夏季の防止乳量差</dt><dd>3.0kg／頭・日", response.text)
        self.assertIn("industry_guidance", response.text)
        self.assertIn("demo_assumption", response.text)
        self.assertIn("この条件で払える目安", response.text)
        self.assertIn("見積額との差", response.text)
        self.assertIn("マイナスなら標準見積が払える目安を上回り", response.text)


if __name__ == "__main__":
    unittest.main()

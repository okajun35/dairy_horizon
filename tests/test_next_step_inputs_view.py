from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from app.main import _dashboard, app


def _next_step(html: str) -> str:
    start = html.find('<section class="next-step')
    end = html.find('<details class="comparison-conditions"', start)
    if start < 0 or end < 0:
        raise AssertionError("next-step section was not rendered")
    return html[start:end]


def _comparison_conditions(html: str) -> str:
    match = re.search(
        r'<details class="comparison-conditions".*?</details>',
        html,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("comparison-conditions section was not rendered")
    return match.group(0)


def _choice_card(html: str, key: str) -> str:
    match = re.search(
        rf'<article class="right-sized-choice-card[^>]*data-choice-card="{key}".*?</article>',
        html,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"right-sized choice was not rendered: {key}")
    return match.group(0)


class NextStepInputsViewTest(unittest.TestCase):
    def test_answering_primary_question_shows_deterministic_before_after_delta(self) -> None:
        previous_state = _dashboard(60, 2, 10, None, 2026)["delta_snapshot"]
        response = TestClient(app).get(
            "/check",
            params={
                "future_target_cow_count": 45,
                "answered_key": "future_target_cow_count",
                "previous_state": previous_state,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('data-answer-delta="future_target_cow_count"', response.text)
        self.assertIn("回答を反映した結果", response.text)
        self.assertIn("5年後の対策対象頭数", response.text)
        self.assertIn("未確認", response.text)
        self.assertIn("45頭", response.text)
        self.assertIn("変わらないもの", response.text)

    def test_step_four_compares_a_right_sized_choice_before_field_handoff(self) -> None:
        page = TestClient(app).get("/check").text
        section = _next_step(page)

        self.assertIn("今年、どこまで整えるかを比べます", section)
        self.assertIn("今のまま", section)
        self.assertIn("まず不足箇所を整える", section)
        self.assertIn("牛舎全体を整える", section)
        self.assertIn("先に払う額", section)
        self.assertIn("残る未カバー推計", section)
        self.assertIn("年間の比較結果", section)
        self.assertIn('data-next-step-plan="current"', section)
        self.assertIn('data-next-step-plan="first_phase"', section)
        self.assertIn('data-next-step-plan="full_coverage"', section)
        self.assertIn('class="step-four-workspace"', section)
        self.assertIn('class="step-four-barn-panel"', section)
        self.assertIn("不足箇所案から見る", section)
        self.assertNotIn("不足箇所から始める", section)
        self.assertNotIn("今、全体整備まで進める", section)
        self.assertIn("1台＝3頭は不足を見つけるための目安", page)
        self.assertIn('id="next-step-barn-viewer"', page)
        self.assertIn("まず整える場合の牛舎", page)
        self.assertIn("その場所のファンが動いているか", page)
        self.assertNotIn('data-primary-input=', section)
        self.assertNotIn("比較条件を更新", section)

    def test_step_four_keeps_cost_and_remaining_uncertainty_together(self) -> None:
        response = TestClient(app).get("/check?avoided_milk_loss_kg_per_cow_day=3")

        current = _choice_card(response.text, "current")
        self.assertIn("先に払う額</dt><dd>0円", current)
        self.assertIn("残る未カバー推計</dt><dd>30頭", current)
        self.assertIn("年間の比較結果</dt><dd", current)
        self.assertIn("基準（0円）", current)

        first_phase = _choice_card(response.text, "first_phase")
        self.assertIn("先に払う額</dt><dd>1,100,000円", first_phase)
        self.assertIn("残る未カバー推計</dt><dd>15頭", first_phase)
        self.assertIn("-46,552円", first_phase)
        self.assertIn("年間差の計算を見る", first_phase)
        self.assertIn("乳量効果の見込み", first_phase)
        self.assertIn("残る効果", first_phase)
        self.assertIn("設備費の年割りと追加電気代", first_phase)
        self.assertIn("追加電気代", first_phase)
        self.assertIn("年間の比較結果", first_phase)

        full_coverage = _choice_card(response.text, "full_coverage")
        self.assertIn("先に払う額</dt><dd>2,200,000円", full_coverage)
        self.assertIn("残る未カバー推計</dt><dd>0頭", full_coverage)
        self.assertIn("-93,105円", full_coverage)

    def test_all_result_side_inputs_are_in_one_anchor_returning_form(self) -> None:
        response = TestClient(app).get(
            "/check?future_target_cow_count=45"
            "&confirmed_covered_cow_count=12"
            "&avoided_milk_loss_kg_per_cow_day=2.5"
            "&milk_price_yen_per_kg=150"
            "&electricity_price_yen_per_kwh=30"
            "&operating_hours_per_day=12"
            "&current_annual_shipped_milk_kg=600000"
            "&future_annual_shipped_milk_kg=450000"
            "&first_phase_fan_count=4"
            "&planned_fan_count=18"
            "&investment_year=2028"
        )

        section = _comparison_conditions(response.text)
        self.assertIn(
            '<form class="next-step-inputs" method="get" action="/check#comparison-conditions">',
            section,
        )
        for input_name in (
            "future_target_cow_count",
            "confirmed_covered_cow_count",
            "avoided_milk_loss_kg_per_cow_day",
            "milk_price_yen_per_kg",
            "electricity_price_yen_per_kwh",
            "operating_hours_per_day",
            "current_annual_shipped_milk_kg",
            "future_annual_shipped_milk_kg",
            "first_phase_fan_count",
            "planned_fan_count",
            "investment_year",
        ):
            self.assertIn(f'name="{input_name}"', section)

        self.assertNotIn('<form class="future-herd-control"', response.text)
        self.assertNotIn('<form class="coverage-control"', response.text)
        self.assertNotIn('<form class="operating-hours-control"', response.text)
        self.assertNotIn('<form class="first-phase-control"', response.text)

    def test_reference_state_keeps_actual_fan_count_in_detailed_conditions(self) -> None:
        section = _comparison_conditions(
            TestClient(app).get(
                "/check?lactating_cows=100&lane_count=4"
                "&existing_fan_count=34&reference_mode=true"
            ).text
        )

        self.assertIn('name="existing_fan_count"', section)
        self.assertIn("現在使っているファン台数", section)
        self.assertNotIn('name="reference_mode"', section)

    def test_blank_standard_placeholders_do_not_change_the_step_four_handoff(self) -> None:
        client = TestClient(app)
        common_blank_details = {
            "confirmed_covered_cow_count": "",
            "operating_hours_per_day": "",
            "avoided_milk_loss_kg_per_cow_day": "",
            "milk_price_yen_per_kg": "",
            "electricity_price_yen_per_kwh": "",
        }

        after_future = client.get(
            "/check",
            params=common_blank_details | {"future_target_cow_count": "45"},
        )
        after_coverage = client.get(
            "/check",
            params=common_blank_details
            | {
                "future_target_cow_count": "45",
                "confirmed_covered_cow_count": "12",
            },
        )

        self.assertEqual(after_future.status_code, 200)
        for response in (after_future, after_coverage):
            section = _next_step(response.text)
            self.assertIn("今年、どこまで整えるかを比べます", section)
            self.assertIn("不足箇所案から見る", section)
            self.assertIn("この画面で見ること", section)
            self.assertNotIn('data-primary-input=', section)


if __name__ == "__main__":
    unittest.main()

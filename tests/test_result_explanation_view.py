from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import _dashboard, _step_four_pathway_view, app, get_result_explainer
from app.result_explanation import (
    ChoiceSummary,
    ResultExplanation,
    ResultExplanationUnavailable,
)


FORM_DATA = {
    "region_ja": "千葉市",
    "lactating_cows": "60",
    "lane_count": "2",
    "existing_fan_count": "10",
    "first_phase_fan_count": "5",
    "investment_year": "2026",
    "planned_fan_count": "20",
    "reference_mode": "false",
    "operating_hours_per_day": "12",
    "future_target_cow_count": "45",
}


class ResultExplanationViewTest(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_normal_get_does_not_call_openai(self) -> None:
        class UnexpectedExplainer:
            def explain(self, _payload: dict[str, object]) -> ResultExplanation:
                raise AssertionError("GET must not call OpenAI")

        app.dependency_overrides[get_result_explainer] = lambda: UnexpectedExplainer()

        response = TestClient(app).get("/check")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('data-choice-summary', response.text)
        self.assertIn("仮置きの乳量効果 +236,318円／年", response.text)
        self.assertIn("不足箇所案から見る", response.text)
        self.assertNotIn('action="/explain#result-explanation"', response.text)

    def test_step_four_primary_text_is_deterministic_for_all_four_positions(self) -> None:
        def pathway_view(
            *,
            current_remaining: int,
            first_remaining: int,
            full_remaining: int,
            first_upfront: int = 1_100_000,
            full_upfront: int = 2_200_000,
            first_annual: int = -46_552,
            full_annual: int = -93_105,
        ) -> dict[str, object]:
            return _step_four_pathway_view(
                financial_comparison={
                    "plans": (
                        {"key": "first_phase", "incremental_capex_yen": first_upfront},
                        {"key": "full_coverage", "incremental_capex_yen": full_upfront},
                    )
                },
                annual_heat_path_comparison={
                    "plans": (
                        {
                            "key": "current",
                            "remaining_uncovered_cow_count": current_remaining,
                            "improvement_vs_no_action_yen": 0,
                        },
                        {
                            "key": "first_phase",
                            "remaining_uncovered_cow_count": first_remaining,
                            "improvement_vs_no_action_yen": first_annual,
                            "annual_contribution_benefit_ja": "+236,318円",
                            "annualized_capex_ja": "-157,143円",
                            "annual_electricity_ja": "-125,727円",
                            "improvement_vs_no_action_ja": "-46,552円",
                        },
                        {
                            "key": "full_coverage",
                            "remaining_uncovered_cow_count": full_remaining,
                            "improvement_vs_no_action_yen": full_annual,
                            "annual_contribution_benefit_ja": "+472,635円",
                            "annualized_capex_ja": "-314,286円",
                            "annual_electricity_ja": "-251,454円",
                            "improvement_vs_no_action_ja": "-93,105円",
                        },
                    )
                },
            )

        views = {
            "START_SMALL": pathway_view(
                current_remaining=30, first_remaining=15, full_remaining=0
            ),
            "MAINTAIN": pathway_view(
                current_remaining=0, first_remaining=0, full_remaining=0,
                first_upfront=0, full_upfront=0, first_annual=0, full_annual=0,
            ),
            "COMPLETE_NOW": pathway_view(
                current_remaining=30, first_remaining=15, full_remaining=0,
                first_upfront=2_200_000, full_upfront=2_200_000,
                first_annual=12_000, full_annual=20_000,
            ),
            "REASSESS": pathway_view(
                current_remaining=30, first_remaining=30, full_remaining=0
            ),
        }

        self.assertEqual(views["START_SMALL"]["policy"]["overall_position"], "START_SMALL")  # type: ignore[index]
        self.assertEqual(views["START_SMALL"]["title_ja"], "不足箇所案から見る")
        self.assertEqual(views["START_SMALL"]["screen_heading_ja"], "この画面で見ること")
        self.assertIn("乳量効果 +236,318円", views["START_SMALL"]["financial_reading_ja"])
        self.assertIn("まかないきれません", views["START_SMALL"]["financial_reading_ja"])
        self.assertEqual(views["MAINTAIN"]["policy"]["overall_position"], "MAINTAIN")  # type: ignore[index]
        self.assertEqual(views["MAINTAIN"]["default_barn_plan"], "current")
        self.assertEqual(views["COMPLETE_NOW"]["policy"]["overall_position"], "COMPLETE_NOW")  # type: ignore[index]
        self.assertEqual(views["COMPLETE_NOW"]["default_barn_plan"], "full_coverage")
        self.assertEqual(views["COMPLETE_NOW"]["screen_heading_ja"], "この画面で見ること")
        self.assertEqual(views["REASSESS"]["policy"]["overall_position"], "REASSESS")  # type: ignore[index]
        self.assertIn("減らない", views["REASSESS"]["summary_ja"])

    def test_choice_summary_endpoint_uses_three_choice_payload_and_fallback(self) -> None:
        captured: dict[str, object] = {}

        class FakeExplainer:
            def summarize_choices(self, payload: dict[str, object]) -> ChoiceSummary:
                captured.update(payload)
                return ChoiceSummary(
                    guardrail_ja="年間比較は追加なしを下回ります。農場全体の赤字や投資の失敗を意味せず、追加費用を年間効果で回収できる確認ではありません。",
                    source_kind="ai_summary",
                )

        app.dependency_overrides[get_result_explainer] = lambda: FakeExplainer()
        state = _dashboard(60, 2, 10, None, 2026)["delta_snapshot"]
        response = TestClient(app).post("/choice-summary", json={"state": state})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["comparison"]["cards"][0]["key"], "current")  # type: ignore[index]
        self.assertEqual(captured["comparison"]["cards"][1]["key"], "first_phase")  # type: ignore[index]
        self.assertEqual(captured["comparison"]["cards"][0]["reading_facts_ja"]["uncovered_change_ja"], "未カバー推計は現状のまま")  # type: ignore[index]
        self.assertEqual(captured["comparison"]["cards"][1]["reading_facts_ja"]["comparison_role_ja"], "全体を整える前に改善の手応えを確かめる比較")  # type: ignore[index]
        self.assertEqual(captured["comparison"]["cards"][2]["reading_facts_ja"]["spending_scope_ja"], "設備費を広く先に払う")  # type: ignore[index]
        self.assertEqual(captured["pathway_policy"]["overall_position"], "START_SMALL")  # type: ignore[index]
        self.assertEqual(captured["pathway_policy"]["economic_guardrail"], "first_phase_annual_comparison_negative")  # type: ignore[index]
        self.assertEqual(captured["economic_guardrail_fact_ja"], "不足箇所案の年間比較は追加なしを下回る。")  # type: ignore[index]
        self.assertEqual(captured["decision_facts_ja"]["observation_discriminator_ja"], "未カバー推計の牛床が一部の困りごとか、牛舎全体に広がる困りごとか")  # type: ignore[index]
        self.assertIn("全体案は不足箇所案より年間比較の負担が大きい", captured["decision_facts_ja"]["annual_relation_ja"])  # type: ignore[index]
        self.assertFalse(captured["boundaries"]["recommend_single_plan"])  # type: ignore[index]
        self.assertEqual(response.json()["summary"]["source_kind"], "ai_summary")

    def test_choice_summary_endpoint_uses_deterministic_fallback_when_ai_fails(self) -> None:
        class FailingExplainer:
            def summarize_choices(self, _payload: dict[str, object]) -> ChoiceSummary:
                raise ResultExplanationUnavailable("provider detail")

        app.dependency_overrides[get_result_explainer] = lambda: FailingExplainer()
        state = _dashboard(60, 2, 10, None, 2026)["delta_snapshot"]
        response = TestClient(app).post("/choice-summary", json={"state": state})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source_kind"], "template_fallback")
        self.assertIn("年間比較は追加なしを下回", response.json()["summary"]["guardrail_ja"])
        self.assertNotIn("provider detail", response.text)

    def test_explain_route_passes_deterministic_payload_and_renders_answer(self) -> None:
        captured: dict[str, object] = {}

        class FakeExplainer:
            def explain(self, payload: dict[str, object]) -> ResultExplanation:
                captured.update(payload)
                return ResultExplanation(
                    headline_ja="小さく始める案と全体案を条件で比べます。",
                    interpretation_ja="不足の改善と運転負担を分けて確認できます。",
                    condition_ja="暑熱期間の幅に応じて運転費も変わります。",
                    next_check_key="cow_level_wind_speed",
                    next_check_ja="設置候補範囲の牛体付近風速",
                    source_kind="ai_explanation",
                )

        app.dependency_overrides[get_result_explainer] = lambda: FakeExplainer()

        response = TestClient(app).post("/explain", data=FORM_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["input"]["lactating_cows"], 60)  # type: ignore[index]
        self.assertEqual(captured["current"]["fan_shortage"], 10)  # type: ignore[index]
        self.assertEqual(captured["plans"][0]["additional_fan_count"], 5)  # type: ignore[index]
        self.assertEqual(captured["plans"][0]["standard_annual_electricity_yen"], 89520)  # type: ignore[index]
        self.assertEqual(captured["annual_heat_path"]["plans"][0]["key"], "current")  # type: ignore[index]
        self.assertEqual(captured["annual_heat_path"]["plans"][0]["remaining_uncovered_cow_count"], 30)  # type: ignore[index]
        self.assertEqual(captured["annual_heat_path"]["plans"][0]["remaining_milk_loss_kg"], 8752.5)  # type: ignore[index]
        self.assertEqual(captured["annual_heat_path"]["plans"][1]["key"], "first_phase")  # type: ignore[index]
        self.assertIn("improvement_vs_no_action_yen", captured["annual_heat_path"]["plans"][1])  # type: ignore[index]
        self.assertEqual(captured["climate"]["operating_hours_per_day"], 12.0)  # type: ignore[index]
        self.assertEqual(captured["climate"]["observed_baseline"]["lower_annual_days"], 97.0)  # type: ignore[index]
        self.assertAlmostEqual(captured["climate"]["periods"][0]["median_annual_days"], 104.5666666667)  # type: ignore[index]
        self.assertFalse(captured["boundaries"]["climate_changes_fan_count"])  # type: ignore[index]
        self.assertEqual(captured["future"]["target_cow_count"], 45)  # type: ignore[index]
        self.assertEqual(captured["decision_context"]["next_check_key"], "cow_level_wind_speed")  # type: ignore[index]
        self.assertNotIn('data-choice-summary', response.text)
        self.assertIn(
            '<form class="next-step-inputs" method="get" action="/check#comparison-conditions">',
            response.text,
        )
        self.assertIn('name="confirmed_covered_cow_count" type="number"', response.text)
        self.assertIn("比較条件を更新", response.text)
        self.assertNotIn('action="/explain#result-explanation"', response.text)
        self.assertNotIn('<form class="operating-hours-control"', response.text)
        self.assertNotIn('<form class="first-phase-control"', response.text)
        self.assertIn(
            '<form class="quick-inputs" method="get" action="/check#step-2">',
            response.text,
        )

    def test_api_failure_uses_deterministic_fallback(self) -> None:
        class FailingExplainer:
            def explain(self, _payload: dict[str, object]) -> ResultExplanation:
                raise ResultExplanationUnavailable("provider detail")

        app.dependency_overrides[get_result_explainer] = lambda: FailingExplainer()

        response = TestClient(app).post("/explain", data=FORM_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('data-choice-summary', response.text)
        self.assertNotIn('action="/explain#result-explanation"', response.text)
        self.assertNotIn("provider detail", response.text)


if __name__ == "__main__":
    unittest.main()

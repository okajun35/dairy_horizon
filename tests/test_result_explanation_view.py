from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app, get_result_explainer
from app.result_explanation import ResultExplanation, ResultExplanationUnavailable


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
}


class ResultExplanationViewTest(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_normal_get_does_not_call_openai(self) -> None:
        class UnexpectedExplainer:
            def explain(self, _payload: dict[str, object]) -> ResultExplanation:
                raise AssertionError("GET must not call OpenAI")

        app.dependency_overrides[get_result_explainer] = lambda: UnexpectedExplainer()

        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AIで計算結果を読み解く", response.text)
        self.assertNotIn("AIによる読み解き", response.text)

    def test_explain_route_passes_deterministic_payload_and_renders_answer(self) -> None:
        captured: dict[str, object] = {}

        class FakeExplainer:
            def explain(self, payload: dict[str, object]) -> ResultExplanation:
                captured.update(payload)
                return ResultExplanation(
                    headline_ja="小さく始める案と全体案を条件で比べます。",
                    interpretation_ja="不足の改善と運転負担を分けて確認できます。",
                    condition_ja="暑熱期間の幅に応じて運転費も変わります。",
                    next_check_key="equipment_quote",
                    next_check_ja="実際の設備見積額",
                    source_kind="ai_explanation",
                )

        app.dependency_overrides[get_result_explainer] = lambda: FakeExplainer()

        response = TestClient(app).post("/explain", data=FORM_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["input"]["lactating_cows"], 60)  # type: ignore[index]
        self.assertEqual(captured["current"]["fan_shortage"], 10)  # type: ignore[index]
        self.assertEqual(captured["plans"][0]["additional_fan_count"], 5)  # type: ignore[index]
        self.assertEqual(captured["plans"][0]["standard_annual_electricity_yen"], 89520)  # type: ignore[index]
        self.assertEqual(captured["climate"]["operating_hours_per_day"], 12.0)  # type: ignore[index]
        self.assertEqual(captured["climate"]["observed_baseline"]["lower_annual_days"], 97.0)  # type: ignore[index]
        self.assertAlmostEqual(captured["climate"]["periods"][0]["median_annual_days"], 104.5666666667)  # type: ignore[index]
        self.assertFalse(captured["boundaries"]["climate_changes_fan_count"])  # type: ignore[index]
        self.assertIn("AIによる読み解き", response.text)
        self.assertIn("現在は頭数目安より10台少なく、未カバー推計は30頭です", response.text)
        self.assertIn("第1期は5台追加で15頭を新たにカバー", response.text)
        self.assertIn("現在相当は97〜98日／年", response.text)
        self.assertIn("暑い日の平均運転時間は12時間／日です", response.text)
        self.assertIn("2026〜2030年の暑熱対象日は中心目安104〜105日", response.text)
        self.assertIn("小さく始める案と全体案を条件で比べます", response.text)
        self.assertIn("次に確認する一件</dt><dd>実際の設備見積額", response.text)
        self.assertIn("ai_explanation", response.text)
        self.assertIn(
            '<form class="operating-hours-control" method="get" action="/">',
            response.text,
        )
        self.assertIn(
            '<form class="first-phase-control" method="get" action="/">',
            response.text,
        )
        self.assertIn(
            '<form class="quick-inputs" method="get" action="/">',
            response.text,
        )

    def test_api_failure_uses_deterministic_fallback(self) -> None:
        class FailingExplainer:
            def explain(self, _payload: dict[str, object]) -> ResultExplanation:
                raise ResultExplanationUnavailable("provider detail")

        app.dependency_overrides[get_result_explainer] = lambda: FailingExplainer()

        response = TestClient(app).post("/explain", data=FORM_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertIn("AI説明を利用できなかったため、計算結果から定型文を表示しています", response.text)
        self.assertIn("計算結果を条件ごとに確認します", response.text)
        self.assertIn("template_fallback", response.text)
        self.assertNotIn("provider detail", response.text)


if __name__ == "__main__":
    unittest.main()

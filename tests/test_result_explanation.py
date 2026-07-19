from __future__ import annotations

import json
import os
import unittest

import httpx

from app.result_explanation import (
    ChoiceSummary,
    OpenAIResultExplainer,
    ResultExplanationUnavailable,
)


def _response_payload(output: dict[str, object]) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(output, ensure_ascii=False),
                    }
                ],
            }
        ],
    }


SAMPLE_PAYLOAD = {
    "input": {
        "region_ja": "千葉市",
        "lactating_cows": 60,
        "existing_fan_count": 10,
        "reference_mode": False,
    },
    "current": {
        "guideline_fan_count": 20,
        "fan_shortage": 10,
        "uncovered_cow_count": 30,
    },
    "plans": [
        {
            "key": "first_phase",
            "additional_fan_count": 5,
            "newly_covered_cow_count": 15,
            "capex_yen": 1100000,
        }
    ],
    "climate": {
        "thi_threshold": 72.0,
        "periods": [
            {
                "start_year": 2026,
                "end_year": 2030,
                "median_annual_days": 96.2,
                "minimum_annual_days": 81.6,
                "maximum_annual_days": 102.6,
            }
        ],
    },
    "boundaries": {
        "climate_changes_fan_count": False,
        "recommend_investment_year": False,
    },
    "decision_context": {"next_check_key": "operating_hours"},
}


class OpenAIResultExplainerTest(unittest.TestCase):
    def test_retries_a_temporary_api_failure_once(self) -> None:
        request_count = 0
        delays: list[float] = []

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                return httpx.Response(503, json={"error": {"message": "busy"}})
            return httpx.Response(
                200,
                json=_response_payload(
                    {
                        "headline_ja": "計算結果を条件ごとに確認します。",
                        "interpretation_ja": "牛舎の不足と追加案の変化を分けて確認できます。",
                        "condition_ja": "年間比較は条件によって変わります。",
                        "next_check_key": "operating_hours",
                    }
                ),
            )

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=delays.append,
        )

        result = explainer.explain(SAMPLE_PAYLOAD)

        self.assertEqual(result.source_kind, "ai_explanation")
        self.assertEqual(request_count, 2)
        self.assertEqual(delays, [0.25])

    def test_does_not_retry_an_authentication_failure(self) -> None:
        request_count = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(401, json={"error": {"message": "invalid key"}})

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _delay: self.fail("authentication failures must not retry"),
        )

        with self.assertRaises(ResultExplanationUnavailable):
            explainer.explain(SAMPLE_PAYLOAD)

        self.assertEqual(request_count, 1)

    def test_regenerates_an_unsafe_structured_output_once(self) -> None:
        request_count = 0
        delays: list[float] = []

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                output = {
                    "headline_ja": "追加は七台がおすすめです。",
                    "interpretation_ja": "不足を解消します。",
                    "condition_ja": "比較条件です。",
                    "next_check_key": "operating_hours",
                }
            else:
                output = {
                    "headline_ja": "計算結果を条件ごとに確認します。",
                    "interpretation_ja": "牛舎の不足と追加案の変化を分けて確認できます。",
                    "condition_ja": "年間比較は条件によって変わります。",
                    "next_check_key": "operating_hours",
                }
            return httpx.Response(200, json=_response_payload(output))

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=delays.append,
        )

        result = explainer.explain(SAMPLE_PAYLOAD)

        self.assertEqual(result.source_kind, "ai_explanation")
        self.assertEqual(request_count, 2)
        self.assertEqual(delays, [0.1])

    def test_sends_only_structured_calculation_results_and_parses_output(self) -> None:
        captured_request: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_request.update(json.loads(request.content))
            return httpx.Response(
                200,
                json=_response_payload(
                    {
                        "headline_ja": "小さく始める案と全体案を条件で比べます。",
                        "interpretation_ja": "牛舎の不足と将来の運転負担を分けて確認できます。",
                        "condition_ja": "暑熱期間にはモデル間の幅があるため、運転費にも幅があります。",
                        "next_check_key": "operating_hours",
                    }
                ),
            )

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        result = explainer.explain(SAMPLE_PAYLOAD)

        self.assertEqual(result.source_kind, "ai_explanation")
        self.assertEqual(result.next_check_key, "operating_hours")
        self.assertEqual(result.next_check_ja, "暑い日の実際の運転時間")
        self.assertEqual(captured_request["model"], "gpt-5.6-luna")
        self.assertFalse(captured_request["store"])
        self.assertEqual(captured_request["reasoning"], {"effort": "none"})
        self.assertNotIn("tools", captured_request)
        self.assertEqual(
            captured_request["text"]["format"]["type"],  # type: ignore[index]
            "json_schema",
        )
        self.assertTrue(captured_request["text"]["format"]["strict"])  # type: ignore[index]
        self.assertNotIn(
            "equipment_quote",
            captured_request["text"]["format"]["schema"]["properties"]["next_check_key"]["enum"],  # type: ignore[index]
        )
        self.assertEqual(json.loads(captured_request["input"]), SAMPLE_PAYLOAD)

    def test_summarizes_three_precalculated_choices_without_recommending_one(self) -> None:
        captured_request: dict[str, object] = {}
        captured_timeout: dict[str, object] = {}
        choice_payload = {
            "pathway_policy": {
                "overall_position": "START_SMALL",
                "uncovered_change": "partial_reduction",
                "path_flexibility": "high",
                "economic_guardrail": "first_phase_annual_comparison_negative",
                "basis": [
                    "first_phase_reduces_uncovered",
                    "full_coverage_reduces_uncovered_further",
                    "first_phase_annual_comparison_negative",
                ],
            },
            "economic_guardrail_fact_ja": "不足箇所案の年間比較は追加なしを下回る。",
            "comparison": {
                "cards": [
                    {"key": "current", "annual_comparison_status": "baseline"},
                    {"key": "first_phase", "annual_comparison_status": "negative"},
                    {"key": "full_coverage", "annual_comparison_status": "negative"},
                ]
            },
            "boundaries": {"recommend_single_plan": False},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            captured_request.update(json.loads(request.content))
            captured_timeout.update(request.extensions["timeout"])
            return httpx.Response(
                200,
                json=_response_payload(
                    {
                        "guardrail_ja": "年間比較は追加なしを下回ります。農場全体の赤字や投資の失敗を意味せず、追加費用を年間効果で回収できる確認ではありません。",
                    }
                ),
            )

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        result = explainer.summarize_choices(choice_payload)

        self.assertIsInstance(result, ChoiceSummary)
        self.assertEqual(result.source_kind, "ai_summary")
        self.assertFalse(captured_request["store"])
        self.assertEqual(captured_request["reasoning"], {"effort": "high"})
        self.assertEqual(captured_request["max_output_tokens"], 4096)
        self.assertEqual(captured_timeout["read"], 45.0)
        self.assertEqual(json.loads(captured_request["input"]), choice_payload)
        self.assertIn("費用面のガードレールだけ", captured_request["instructions"])
        self.assertIn("進め方、案のおすすめ、二択、牛舎図", captured_request["instructions"])
        schema = captured_request["text"]["format"]["schema"]  # type: ignore[index]
        self.assertEqual(schema["properties"]["guardrail_ja"]["maxLength"], 160)  # type: ignore[index]

    def test_generated_explanation_cannot_introduce_numeric_claims(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_response_payload(
                    {
                        "headline_ja": "追加は七台がおすすめです。",
                        "interpretation_ja": "不足を解消します。",
                        "condition_ja": "確実に回収できます。",
                        "next_check_key": "operating_hours",
                    }
                ),
            )

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        with self.assertRaises(ResultExplanationUnavailable):
            explainer.explain(SAMPLE_PAYLOAD)

    def test_choice_summary_rejects_a_guardrail_that_conflicts_with_python(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_response_payload(
                    {
                        "guardrail_ja": "年間比較は追加なしを下回っていません。投資回収の保証ではありません。",
                    }
                ),
            )

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        with self.assertRaises(ResultExplanationUnavailable):
            explainer.summarize_choices(
                {
                    "pathway_policy": {
                        "economic_guardrail": "first_phase_annual_comparison_negative"
                    }
                }
            )

    def test_choice_summary_rejects_text_beyond_a_field_budget(self) -> None:
        raw = {
            "guardrail_ja": "あ" * 161,
        }

        with self.assertRaises(ValueError):
            OpenAIResultExplainer._validated_choice_summary(raw)

    def test_choice_summary_log_identifies_the_rejected_field(self) -> None:
        invalid_output = {
            "guardrail_ja": "あ" * 161,
        }

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_response_payload(invalid_output))

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _delay: None,
        )

        with self.assertLogs("app.result_explanation", level="WARNING") as logs:
            with self.assertRaises(ResultExplanationUnavailable):
                explainer.summarize_choices({"comparison": {"cards": []}})

        self.assertIn("field=guardrail_ja reason=length", logs.output[0])

    def test_api_errors_do_not_expose_provider_details(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": {"message": "provider secret"}})

        explainer = OpenAIResultExplainer(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        with self.assertRaisesRegex(ResultExplanationUnavailable, "説明を生成できません") as caught:
            explainer.explain(SAMPLE_PAYLOAD)

        self.assertNotIn("provider secret", str(caught.exception))


@unittest.skipUnless(
    os.getenv("RUN_OPENAI_INTEGRATION_TESTS") == "1",
    "Set RUN_OPENAI_INTEGRATION_TESTS=1 to call the live OpenAI API.",
)
class OpenAIResultExplainerLiveTest(unittest.TestCase):
    def test_live_api_explains_structured_results_without_new_numbers(self) -> None:
        result = OpenAIResultExplainer.from_environment().explain(SAMPLE_PAYLOAD)

        self.assertTrue(result.headline_ja)
        self.assertTrue(result.interpretation_ja)
        self.assertTrue(result.condition_ja)
        self.assertEqual(result.next_check_key, "operating_hours")

    def test_live_api_reads_the_default_three_choices_as_a_decision(self) -> None:
        """Keep the actual standard-case wording reviewable without a browser."""

        from app.main import _choice_summary_payload, _dashboard

        payload = _choice_summary_payload(_dashboard(60, 2, 10, None, 2026))
        result = OpenAIResultExplainer.from_environment().summarize_choices(payload)
        text = result.guardrail_ja

        self.assertTrue(result.guardrail_ja)
        self.assertIn("年間比較は追加なしを下回", result.guardrail_ja)
        self.assertNotIn("おすすめ", text)
        self.assertNotIn("回収できる", text)


if __name__ == "__main__":
    unittest.main()

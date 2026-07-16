from __future__ import annotations

import json
import os
import unittest

import httpx

from app.result_explanation import (
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
}


class OpenAIResultExplainerTest(unittest.TestCase):
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
        self.assertIn(result.next_check_key, {"actual_fan_count", "operating_hours"})


if __name__ == "__main__":
    unittest.main()

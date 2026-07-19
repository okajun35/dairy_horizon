"""Manual prompt evaluation for a possible card-selection guidance feature.

This is deliberately separate from the production endpoint.  Run it only when
testing whether the interaction is worth building:

    set -a; source .env; set +a
    RUN_OPENAI_PROMPT_EVALS=1 .venv/bin/python -m unittest \
      tests.test_choice_guidance_prompt_eval -v
"""

from __future__ import annotations

import json
import os
import unittest

import httpx

from app.main import _choice_summary_payload, _dashboard


PROMPT_EVAL_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra")
GUIDANCE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "when_unselected_ja": {"type": "string", "minLength": 1, "maxLength": 160},
        "when_current_selected_ja": {"type": "string", "minLength": 1, "maxLength": 110},
        "when_first_phase_selected_ja": {"type": "string", "minLength": 1, "maxLength": 110},
        "when_full_coverage_selected_ja": {"type": "string", "minLength": 1, "maxLength": 110},
    },
    "required": [
        "when_unselected_ja",
        "when_current_selected_ja",
        "when_first_phase_selected_ja",
        "when_full_coverage_selected_ja",
    ],
}
GUIDANCE_PROMPT = """あなたは酪農の暑熱対策比較画面の文章プロトタイプを評価します。
入力JSONのカードとdecision_facts_jaはPythonが計算済みの事実です。計算、数値の補完、事実の追加をしません。
利用者は現場の困りごとをすでに把握しています。現場確認、風速、牛の状態、専門家への相談を指示しません。

返す文章は、次の二つの利用状態に役立つかを試すものです。
- 未選択: どの案を選べばよいか分からない。
- カード選択後: 自分の選択が何を優先し、他案と何が違うか確かめたい。

when_unselected_jaでは、三案を選ぶ軸だけを平易に説明します。単一案を推薦しません。
when_current_selected_ja、when_first_phase_selected_ja、when_full_coverage_selected_jaでは、
そのカードを選んだ人が優先していることと、残ることを一文ずつで説明します。
「正しい」「おすすめ」「受け入れられる」「確認してください」「投資すべき」を使いません。
画面が案名と数値を表示するため、案名、台数、頭数、金額、年を繰り返しません。
説明のためだけの一般論ではなく、入力の未カバーの変化、先に払う額、年間比較の関係を使います。"""


def _output_text(response_payload: object) -> str:
    if not isinstance(response_payload, dict):
        raise AssertionError("Responses API did not return an object")
    if response_payload.get("status") != "completed":
        raise AssertionError(f"Responses API did not complete: {response_payload.get('status')}")
    for item in response_payload.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    return text
    raise AssertionError("Responses API did not return output text")


@unittest.skipUnless(
    os.getenv("RUN_OPENAI_PROMPT_EVALS") == "1",
    "Set RUN_OPENAI_PROMPT_EVALS=1 to run this paid prompt evaluation.",
)
class ChoiceGuidancePromptEvalTest(unittest.TestCase):
    def test_default_case_for_luna_and_terra(self) -> None:
        api_key = os.environ["OPENAI_API_KEY"]
        payload = _choice_summary_payload(_dashboard(60, 2, 10, None, 2026))
        for model in PROMPT_EVAL_MODELS:
            with self.subTest(model=model), httpx.Client(timeout=45.0) as client:
                response = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "instructions": GUIDANCE_PROMPT,
                        "input": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        "reasoning": {"effort": "high"},
                        "max_output_tokens": 4096,
                        "store": False,
                        "text": {
                            "verbosity": "low",
                            "format": {
                                "type": "json_schema",
                                "name": "choice_guidance_prompt_eval",
                                "strict": True,
                                "schema": GUIDANCE_SCHEMA,
                            },
                        },
                    },
                )
            response.raise_for_status()
            response_payload = response.json()
            text = _output_text(response_payload)
            result = json.loads(text)
            combined = " ".join(result.values())

            self.assertEqual(set(result), set(GUIDANCE_SCHEMA["required"]))
            self.assertTrue(all(value.strip() for value in result.values()))
            self.assertNotIn("おすすめ", combined)
            self.assertNotIn("正しい", combined)
            self.assertNotIn("受け入れられる", combined)
            self.assertNotIn("確認してください", combined)
            print(f"\n[{model}]\n{json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    unittest.main()

"""Manual model evaluation for the proposed Step 4 decision copy.

This is intentionally separate from production.  Do not connect the prompt or
schema to the page unless a human approves the printed result.
"""

from __future__ import annotations

import json
import os
import unittest

import httpx

from tests.test_choice_guidance_prompt_eval import _output_text


PROMPT_EVAL_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra")
STEP_FOUR_DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title_ja": {"type": "string", "minLength": 1, "maxLength": 50},
        "summary_ja": {"type": "string", "minLength": 1, "maxLength": 120},
        "guardrail_ja": {"type": "string", "minLength": 1, "maxLength": 220},
        "screen_focus_ja": {"type": "string", "minLength": 1, "maxLength": 120},
        "choice_presentation_ja": {"type": "string", "minLength": 1, "maxLength": 140},
    },
    "required": [
        "title_ja",
        "summary_ja",
        "guardrail_ja",
        "screen_focus_ja",
        "choice_presentation_ja",
    ],
}
STEP_FOUR_DECISION_PROMPT = """あなたは酪農の暑熱対策比較画面の文章を、決定済みのPython policyから作ります。
これは画面実装前の文章評価です。入力にない判断を足さず、投資を実行させたり、見積もり・業者・現場作業を求めたりしません。
未カバー推計は配置計算の結果であり、実測風速や冷却の保証ではありません。

overall_positionにより、主表示を次のように変えます。
- START_SMALL: 「まず不足箇所から改善する案」。不足箇所案を検討の基準にし、未カバー推計を減らしながら全体整備を今すぐ確定しない。
- MAINTAIN: 「今の配置を保つ状態」。配置計算で未カバー推計がないため、追加設備を急いで決めない。
- COMPLETE_NOW: 「今、全体まで整える案」。全体案が不足箇所案より比較上不利でなく、未カバー推計を残さない進め方も成り立つ。
- REASSESS: 「条件を見直してから決める案」。不足箇所案では未カバー推計が減らないため、二択の前に配置または台数条件を見直す。

各フィールドの役割を重複させません。
- title_ja: 進め方の見出しだけ。
- summary_ja: その状態で今決めること、または決めないことを一文で説明する。
- guardrail_ja: 入力facts_jaの年間比較の意味だけを二文以内で示す。negativeなら農場全体の赤字・投資失敗ではないことと、追加費用を年間効果で回収できる確認ではないことを含める。not_applicableなら追加設備の年間比較が当てはまらないことを示す。not_negativeなら投資回収の保証ではないことを示す。
- screen_focus_ja: この画面で見る牛舎図の一点だけを書く。
- choice_presentation_ja: START_SMALLとCOMPLETE_NOWでは「不足箇所から始める／今、全体整備まで進める」の二択をこの画面で見比べると書く。MAINTAINとREASSESSでは、二択を出さずに牛舎図を比べると書く。

「おすすめ」「正しい」「投資すべき」「必ず」「見積」「業者」「相談」「第2期」を使いません。金額、頭数、台数、年を出しません。「回収できる」は、回収を保証しない否定文の中でだけ使えます。"""

EVAL_CASES = {
    "START_SMALL": {
        "policy": {"overall_position": "START_SMALL", "economic_guardrail": "negative"},
        "facts_ja": {"annual_guardrail": "不足箇所案の年間比較は追加なしを下回る"},
    },
    "MAINTAIN": {
        "policy": {"overall_position": "MAINTAIN", "economic_guardrail": "not_applicable"},
        "facts_ja": {"annual_guardrail": "追加設備の年間比較は当てはまらない"},
    },
    "COMPLETE_NOW": {
        "policy": {"overall_position": "COMPLETE_NOW", "economic_guardrail": "not_negative"},
        "facts_ja": {"annual_guardrail": "全体案の年間比較は追加なしを下回っていない"},
    },
    "REASSESS": {
        "policy": {"overall_position": "REASSESS", "economic_guardrail": "negative"},
        "facts_ja": {"annual_guardrail": "不足箇所案の年間比較は追加なしを下回る"},
    },
}


@unittest.skipUnless(
    os.getenv("RUN_OPENAI_STEP_FOUR_EVALS") == "1",
    "Set RUN_OPENAI_STEP_FOUR_EVALS=1 to run this paid prompt evaluation.",
)
class StepFourDecisionPromptEvalTest(unittest.TestCase):
    def test_models_can_explain_all_four_pathway_positions(self) -> None:
        api_key = os.environ["OPENAI_API_KEY"]
        for case_name, payload in EVAL_CASES.items():
            for model in PROMPT_EVAL_MODELS:
                with self.subTest(case=case_name, model=model), httpx.Client(timeout=45.0) as client:
                    response = client.post(
                        "https://api.openai.com/v1/responses",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "instructions": STEP_FOUR_DECISION_PROMPT,
                            "input": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            "reasoning": {"effort": "high"},
                            "max_output_tokens": 4096,
                            "store": False,
                            "text": {
                                "verbosity": "low",
                                "format": {
                                    "type": "json_schema",
                                    "name": "step_four_decision_copy_eval",
                                    "strict": True,
                                    "schema": STEP_FOUR_DECISION_SCHEMA,
                                },
                            },
                        },
                    )
                response.raise_for_status()
                result = json.loads(_output_text(response.json()))
                combined = " ".join(result.values())
                print(
                    f"\n[step_four_decision: {case_name} / {model}]\n"
                    f"{json.dumps(result, ensure_ascii=False, indent=2)}"
                )

                self.assertEqual(set(result), set(STEP_FOUR_DECISION_SCHEMA["required"]))
                self.assertTrue(all(value.strip() for value in result.values()))
                self.assertIn("未カバー推計", result["screen_focus_ja"])
                if case_name in {"START_SMALL", "COMPLETE_NOW"}:
                    self.assertIn("二択", result["choice_presentation_ja"])
                else:
                    self.assertTrue(
                        "二択を出さ" in result["choice_presentation_ja"]
                        or "二択は出さ" in result["choice_presentation_ja"]
                    )
                if case_name in {"START_SMALL", "REASSESS"}:
                    self.assertIn("追加なしを下回", result["guardrail_ja"])
                    self.assertTrue(
                        "回収" in result["guardrail_ja"]
                        or "埋め" in result["guardrail_ja"]
                    )
                for forbidden in (
                    "おすすめ",
                    "正しい",
                    "投資すべき",
                    "必ず",
                    "見積",
                    "業者",
                    "相談",
                    "第2期",
                ):
                    self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()

"""Manual evaluation of AI explanations for deterministic decision-policy cases.

This does not change the production UI.  It verifies whether a model can make
the policy's already-determined reading understandable before that feature is
built into the page.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import os
import unittest

import httpx

from app.decision_policy import (
    ComparisonOption,
    DeclaredPriority,
    ThreeChoiceEvidence,
    build_adaptive_pathway_position,
    build_standard_economic_reading,
)
from tests.test_choice_guidance_prompt_eval import _output_text


PROMPT_EVAL_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra")
POLICY_EXPLANATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "standard_reading_ja": {"type": "string", "minLength": 1, "maxLength": 180},
        "current_selected_ja": {"type": "string", "minLength": 1, "maxLength": 120},
        "first_phase_selected_ja": {"type": "string", "minLength": 1, "maxLength": 120},
        "full_coverage_selected_ja": {"type": "string", "minLength": 1, "maxLength": 120},
    },
    "required": [
        "standard_reading_ja",
        "current_selected_ja",
        "first_phase_selected_ja",
        "full_coverage_selected_ja",
    ],
}
POLICY_EXPLANATION_PROMPT = """あなたは酪農の暑熱対策比較画面で、Pythonが決定済みの標準的な経済判断を説明します。
入力のpolicyは決定論的な結論です。policyと異なる結論、単一案のおすすめ、投資年、回収保証を出しません。
この標準判断は経済面の読み方であり、農場全体の赤字、物理的な冷却の十分さ、投資の正しさを示すものではありません。

standard_reading_jaでは、economic_readingとcomparison_focusから、未選択の利用者が最初に読む結論を二文以内で示してください。
current_selected_ja、first_phase_selected_ja、full_coverage_selected_jaでは、そのカードを選んだ利用者に対し、
対応する*_selected_positionを必ず日本語へ反映してください。economically_supportedは「経済面では年間比較が下回っていない」、
partial_coverage_beyond_economic_screenとfull_coverage_beyond_economic_screenは「経済面だけでは支持されない比較」、
economic_baselineは「経済面の基準」と明示します。単に「比較します」「見ます」と言い換えません。
利用者の心理を推測せず、正しい・おすすめ・受け入れられる・確認してください・投資すべきを使いません。
画面が案名と数値を表示するため、案名、台数、頭数、金額、年を繰り返しません。
数字や一般論を並べるだけでなく、policyの経済的な焦点が明確に伝わる文にしてください。"""


def _evidence(first_annual: int, full_annual: int) -> ThreeChoiceEvidence:
    return ThreeChoiceEvidence(
        current=ComparisonOption(0, 30, 0),
        first_phase=ComparisonOption(1_100_000, 15, first_annual),
        full_coverage=ComparisonOption(2_200_000, 0, full_annual),
    )


POLICY_CASES = {
    "both_not_supported": _evidence(-46_552, -93_105),
    "first_phase_only_supported": _evidence(12_000, -8_000),
    "both_supported": _evidence(12_000, 20_000),
}

PRIORITY_EXPLANATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "avoid_unrecovered_spending_ja": {"type": "string", "minLength": 1, "maxLength": 150},
        "avoid_uncovered_cows_ja": {"type": "string", "minLength": 1, "maxLength": 150},
    },
    "required": ["avoid_unrecovered_spending_ja", "avoid_uncovered_cows_ja"],
}
PRIORITY_EXPLANATION_PROMPT = """あなたは酪農の暑熱対策比較画面で、一問だけの優先順位回答を説明します。
入力には、同じ計算結果に対してPythonが作った二つのpolicyがあります。policyは決定済みであり、変更や推薦をしません。
avoid_unrecovered_spending_jaでは「回収が確認できない支出」をより避けたい、と利用者が明示した場合に、
その回答で比較の見方がどう変わるかを二文以内で説明してください。
avoid_uncovered_cows_jaでは「未カバーを残すこと」をより避けたい、と利用者が明示した場合に、
その回答で比較の見方がどう変わるかを二文以内で説明してください。
経済面だけでは支持されない比較を、経済的に成立したかのように書き換えません。
正しい・おすすめ・受け入れられる・確認してください・投資すべきを使わず、案名、台数、頭数、金額、年も繰り返しません。"""


ADAPTIVE_PATHWAY_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "position_ja": {"type": "string", "minLength": 1, "maxLength": 180},
        "reason_ja": {"type": "string", "minLength": 1, "maxLength": 220},
        "guardrail_ja": {"type": "string", "minLength": 1, "maxLength": 160},
        "screen_focus_ja": {"type": "string", "minLength": 1, "maxLength": 120},
    },
    "required": ["position_ja", "reason_ja", "guardrail_ja", "screen_focus_ja"],
}
ADAPTIVE_PATHWAY_PROMPT = """あなたは酪農の暑熱対策比較画面で、Pythonが決定済みの「進め方の位置づけ」を平易に説明します。
主目的は未カバー推計を減らし、将来の選択余地を失わないことです。お金は目的ではなく、進め方を壊さないためのガードレールです。
入力policyを変更、推測、再計算しません。単一案のおすすめ、投資回収の保証、牛が実際に涼しくなる保証、投資年を出しません。
「未カバー」は配置計算による推計であり、風速実測や冷却の十分さではありません。

position_jaは、overall_positionを必ず次の意味で説明します。
- MAINTAIN: 追加設備を急いで決める位置ではない。
- START_SMALL: まず不足箇所で未カバー推計を減らし、全体整備を今確定しない進め方。
- COMPLETE_NOW: 全体案が小さく始める案より比較上悪くないため、一度に整える位置づけも成り立つ。
- REASSESS: 小さく始めても未カバー推計が減らないため、設備案を決める前に条件を見直す位置。

reason_jaはbasisとuncovered_change、path_flexibilityを使い、なぜその位置づけかを二文以内で説明します。
guardrail_jaはeconomic_guardrailを必ず反映します。annual_comparison_negativeなら「年間比較は追加なしを下回る」と明記し、これは農場全体の赤字・投資の失敗を意味しないと続けます。annual_comparison_not_negativeなら「年間比較は追加なしを下回っていない」と明記し、投資回収の保証ではないと続けます。not_applicableなら追加設備の比較を急がないことを明記します。
screen_focus_jaは、利用者へ次の外部行動を求めず、この画面で見比べる一点を示します。START_SMALLでは不足箇所案の牛舎図で未カバー推計がどこまで減るか、REASSESSでは不足箇所案で未カバー推計が減らないこと、MAINTAINでは現在の牛舎図の未カバー推計、COMPLETE_NOWでは全体案で未カバー推計がなくなる位置を扱います。
画面に数値・案名があるため、金額、頭数、台数、年は繰り返しません。「第1期」と書かず「不足箇所案」と書きます。「おすすめ」「正しい」「投資すべき」「必ず」「回収できる」を使いません。"""


ADAPTIVE_PATHWAY_CASES = {
    "standard_start_small": _evidence(-46_552, -93_105),
    "maintain": ThreeChoiceEvidence(
        current=ComparisonOption(0, 0, 0),
        first_phase=ComparisonOption(0, 0, 0),
        full_coverage=ComparisonOption(0, 0, 0),
    ),
    "complete_now_when_full_dominates": ThreeChoiceEvidence(
        current=ComparisonOption(0, 30, 0),
        first_phase=ComparisonOption(2_200_000, 15, 12_000),
        full_coverage=ComparisonOption(2_200_000, 0, 20_000),
    ),
    "reassess_when_small_start_does_not_reduce": ThreeChoiceEvidence(
        current=ComparisonOption(0, 30, 0),
        first_phase=ComparisonOption(1_100_000, 30, -46_552),
        full_coverage=ComparisonOption(2_200_000, 0, -93_105),
    ),
}


@unittest.skipUnless(
    os.getenv("RUN_OPENAI_POLICY_EVALS") == "1",
    "Set RUN_OPENAI_POLICY_EVALS=1 to run this paid prompt evaluation.",
)
class DecisionPolicyPromptEvalTest(unittest.TestCase):
    def test_adaptive_pathway_explanation_for_four_positions_and_two_models(self) -> None:
        api_key = os.environ["OPENAI_API_KEY"]
        labels = {
            "MAINTAIN": "現状を維持する",
            "START_SMALL": "小さく改善して効果を見る",
            "COMPLETE_NOW": "今まとめて整える",
            "REASSESS": "条件を見直してから決める",
            "already_covered": "未カバー推計はすでにない",
            "partial_reduction": "未カバー推計を一部減らす",
            "complete_reduction": "未カバー推計をなくす",
            "no_reduction_from_first_phase": "第1期では未カバー推計が減らない",
            "not_needed": "追加判断を急がない",
            "high": "全体整備を後から選べる",
            "unclear": "小さく始める意味がまだ定まらない",
            "not_applicable": "追加設備の年間比較は当てはまらない",
            "first_phase_annual_comparison_not_negative": "第1期の年間比較は追加なしを下回っていない",
            "first_phase_annual_comparison_negative": "第1期の年間比較は追加なしを下回る",
            "full_coverage_annual_comparison_not_negative": "全体案の年間比較は追加なしを下回っていない",
        }
        for case_name, evidence in ADAPTIVE_PATHWAY_CASES.items():
            policy = build_adaptive_pathway_position(evidence)
            payload = {"policy": asdict(policy), "policy_labels_ja": labels}
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
                            "instructions": ADAPTIVE_PATHWAY_PROMPT,
                            "input": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            "reasoning": {"effort": "high"},
                            "max_output_tokens": 4096,
                            "store": False,
                            "text": {
                                "verbosity": "low",
                                "format": {
                                    "type": "json_schema",
                                    "name": "adaptive_pathway_prompt_eval",
                                    "strict": True,
                                    "schema": ADAPTIVE_PATHWAY_SCHEMA,
                                },
                            },
                        },
                    )
                response.raise_for_status()
                result = json.loads(_output_text(response.json()))
                combined = " ".join(result.values())

                self.assertEqual(set(result), set(ADAPTIVE_PATHWAY_SCHEMA["required"]))
                self.assertTrue(all(value.strip() for value in result.values()))
                for forbidden in ("おすすめ", "正しい", "投資すべき", "必ず", "回収できる", "第1期"):
                    self.assertNotIn(forbidden, combined)
                print(
                    f"\n[adaptive_pathway: {case_name} / {model}]\n"
                    f"{json.dumps(result, ensure_ascii=False, indent=2)}"
                )

    def test_policy_explanation_for_three_economic_cases_and_two_models(self) -> None:
        api_key = os.environ["OPENAI_API_KEY"]
        for case_name, evidence in POLICY_CASES.items():
            policy = build_standard_economic_reading(evidence)
            payload = {
                "policy": asdict(policy),
                "policy_labels_ja": {
                    "additional_options_not_economically_supported": "追加案の年間比較は、現在の条件では追加なしを上回っていない",
                    "first_phase_only_economically_supported": "不足箇所案は年間比較が追加なしを下回らず、全体案は下回っている",
                    "additional_options_economically_supported": "追加案はいずれも年間比較が追加なしを下回っていない",
                    "current_and_first_phase": "追加なしと不足箇所案を比べる",
                    "first_phase_and_full_coverage": "不足箇所案と全体案を比べる",
                    "economic_baseline": "経済面の基準",
                    "economically_supported": "経済面では年間比較が追加なしを下回っていない",
                    "partial_coverage_beyond_economic_screen": "未カバーを一部減らすが、経済面だけでは支持されない比較",
                    "full_coverage_beyond_economic_screen": "未カバーをなくす想定だが、経済面だけでは支持されない比較",
                },
            }
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
                            "instructions": POLICY_EXPLANATION_PROMPT,
                            "input": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            "reasoning": {"effort": "high"},
                            "max_output_tokens": 4096,
                            "store": False,
                            "text": {
                                "verbosity": "low",
                                "format": {
                                    "type": "json_schema",
                                    "name": "decision_policy_prompt_eval",
                                    "strict": True,
                                    "schema": POLICY_EXPLANATION_SCHEMA,
                                },
                            },
                        },
                    )
                response.raise_for_status()
                result = json.loads(_output_text(response.json()))
                combined = " ".join(result.values())

                self.assertEqual(set(result), set(POLICY_EXPLANATION_SCHEMA["required"]))
                self.assertTrue(all(value.strip() for value in result.values()))
                for forbidden in ("おすすめ", "正しい", "受け入れられる", "確認してください", "投資すべき"):
                    self.assertNotIn(forbidden, combined)
                print(
                    f"\n[{case_name} / {model}]\n"
                    f"{json.dumps(result, ensure_ascii=False, indent=2)}"
                )

    def test_declared_priority_changes_the_reading_without_creating_a_recommendation(self) -> None:
        api_key = os.environ["OPENAI_API_KEY"]
        evidence = POLICY_CASES["both_not_supported"]
        payload = {
            "avoid_unrecovered_spending": asdict(
                build_standard_economic_reading(
                    evidence,
                    declared_priority=DeclaredPriority.AVOID_UNRECOVERED_SPENDING,
                )
            ),
            "avoid_uncovered_cows": asdict(
                build_standard_economic_reading(
                    evidence,
                    declared_priority=DeclaredPriority.AVOID_UNCOVERED_COWS,
                )
            ),
            "priority_labels_ja": {
                "spending_priority_declared": "回収が確認できない支出をより避けたいと明示した",
                "coverage_priority_declared": "未カバーを残すことをより避けたいと明示した",
                "economic_baseline": "経済面の基準",
                "partial_coverage_beyond_economic_screen": "未カバーを一部減らすが、経済面だけでは支持されない比較",
                "full_coverage_beyond_economic_screen": "未カバーをなくす想定だが、経済面だけでは支持されない比較",
            },
        }
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
                        "instructions": PRIORITY_EXPLANATION_PROMPT,
                        "input": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        "reasoning": {"effort": "high"},
                        "max_output_tokens": 4096,
                        "store": False,
                        "text": {
                            "verbosity": "low",
                            "format": {
                                "type": "json_schema",
                                "name": "decision_priority_prompt_eval",
                                "strict": True,
                                "schema": PRIORITY_EXPLANATION_SCHEMA,
                            },
                        },
                    },
                )
            response.raise_for_status()
            result = json.loads(_output_text(response.json()))
            combined = " ".join(result.values())

            self.assertEqual(set(result), set(PRIORITY_EXPLANATION_SCHEMA["required"]))
            for forbidden in ("おすすめ", "正しい", "受け入れられる", "確認してください", "投資すべき"):
                self.assertNotIn(forbidden, combined)
            print(
                f"\n[declared_priority / {model}]\n"
                f"{json.dumps(result, ensure_ascii=False, indent=2)}"
            )


if __name__ == "__main__":
    unittest.main()

"""Text-only prototype for the proposed Step 4 decision surface.

This file deliberately does not import a template or alter the page.  It is a
reviewable contract for deciding whether the proposed wording gives the user a
clear path before we build its UI.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import unittest
from typing import Iterable

from app.decision_policy import (
    ComparisonOption,
    ThreeChoiceEvidence,
    build_adaptive_pathway_position,
)


@dataclass(frozen=True)
class StepFourDecisionPrototype:
    title_ja: str
    summary_ja: str
    guardrail_ja: str
    decision_heading_ja: str
    decision_prompt_ja: str


def _standard_evidence() -> ThreeChoiceEvidence:
    return ThreeChoiceEvidence(
        current=ComparisonOption(0, 30, 0),
        first_phase=ComparisonOption(1_100_000, 15, -46_552),
        full_coverage=ComparisonOption(2_200_000, 0, -93_105),
    )


def _all_evidence() -> dict[str, ThreeChoiceEvidence]:
    return {
        "START_SMALL": _standard_evidence(),
        "MAINTAIN": ThreeChoiceEvidence(
            current=ComparisonOption(0, 0, 0),
            first_phase=ComparisonOption(0, 0, 0),
            full_coverage=ComparisonOption(0, 0, 0),
        ),
        "COMPLETE_NOW": ThreeChoiceEvidence(
            current=ComparisonOption(0, 30, 0),
            first_phase=ComparisonOption(2_200_000, 15, 12_000),
            full_coverage=ComparisonOption(2_200_000, 0, 20_000),
        ),
        "REASSESS": ThreeChoiceEvidence(
            current=ComparisonOption(0, 30, 0),
            first_phase=ComparisonOption(1_100_000, 30, -46_552),
            full_coverage=ComparisonOption(2_200_000, 0, -93_105),
        ),
    }


def _prototype_for(policy_position: str) -> StepFourDecisionPrototype:
    """Show all intended text hierarchies without calling a model or rendering UI."""

    if policy_position == "MAINTAIN":
        return StepFourDecisionPrototype(
            title_ja="今の配置から見る",
            summary_ja="配置計算では未カバー推計がないため、追加設備を今すぐ決める状態ではありません。",
            guardrail_ja="追加設備の年間比較は当てはまりません。この結果は実測風速や実際の冷却を保証するものではありません。",
            decision_heading_ja="この画面で見ること",
            decision_prompt_ja="現在の牛舎図で、未カバー推計がない位置を見ます。",
        )
    if policy_position == "COMPLETE_NOW":
        return StepFourDecisionPrototype(
            title_ja="全体案から見る",
            summary_ja="全体案が不足箇所案より比較上不利でないため、未カバー推計を残さない進め方も成り立ちます。",
            guardrail_ja="全体案の年間比較は追加なしを下回っていません。これは投資回収や実際の冷却を保証するものではありません。",
            decision_heading_ja="この画面で見ること",
            decision_prompt_ja="全体案の牛舎図で、未カバー推計がなくなる位置を見ます。",
        )
    if policy_position == "REASSESS":
        return StepFourDecisionPrototype(
            title_ja="比較条件を見直す",
            summary_ja="不足箇所案では未カバー推計が減らないため、配置または台数の条件を見直します。",
            guardrail_ja="不足箇所案の年間比較は追加なしを下回っています。これは農場全体の赤字や投資失敗を示すものではありません。",
            decision_heading_ja="この画面で見ること",
            decision_prompt_ja="現在と不足箇所案の牛舎図を比べ、未カバー推計が減らないことを見ます。",
        )
    return StepFourDecisionPrototype(
        title_ja="不足箇所案から見る",
        summary_ja="未カバー推計を減らしつつ、全体整備を今すぐ確定しない進め方です。",
        guardrail_ja=(
            "今回の年間比較では、不足箇所案は追加なしを下回っています。"
            "これは農場全体の赤字や設備投資の失敗を示すものではありません。"
            "ただし、今回の条件だけでは、追加費用を年間の効果で回収できることも確認できていません。"
        ),
        decision_heading_ja="この画面で見ること",
        decision_prompt_ja="まず不足箇所案で、どの位置の未カバー推計が減るかを確認します。",
    )


def _printable_lines(prototype: StepFourDecisionPrototype) -> Iterable[str]:
    yield prototype.title_ja
    yield prototype.summary_ja
    yield "年間差が出る理由"
    yield prototype.guardrail_ja
    yield prototype.decision_heading_ja
    yield prototype.decision_prompt_ja


class StepFourDecisionPrototypeTest(unittest.TestCase):
    def test_standard_case_has_a_clear_primary_path_without_claiming_recovery(self) -> None:
        policy = build_adaptive_pathway_position(_standard_evidence())
        prototype = _prototype_for(policy.overall_position)

        self.assertEqual(policy.overall_position, "START_SMALL")
        self.assertEqual(prototype.title_ja, "不足箇所案から見る")
        self.assertIn("今すぐ確定しない", prototype.summary_ja)
        self.assertIn("追加なしを下回", prototype.guardrail_ja)
        self.assertIn("回収できることも確認できていません", prototype.guardrail_ja)
        self.assertNotIn("おすすめ", " ".join(vars(prototype).values()))
        self.assertNotIn("見積", " ".join(vars(prototype).values()))

    def test_standard_case_points_to_the_barn_comparison_without_a_path_button(self) -> None:
        prototype = _prototype_for("START_SMALL")

        self.assertEqual(prototype.decision_heading_ja, "この画面で見ること")
        self.assertIn("未カバー推計", prototype.decision_prompt_ja)
        self.assertNotIn("不足箇所から始める", " ".join(vars(prototype).values()))

    def test_all_four_policy_positions_have_a_distinct_text_hierarchy(self) -> None:
        prototypes = {
            key: _prototype_for(build_adaptive_pathway_position(evidence).overall_position)
            for key, evidence in _all_evidence().items()
        }

        self.assertEqual(set(prototypes), {"MAINTAIN", "START_SMALL", "COMPLETE_NOW", "REASSESS"})
        self.assertIn("未カバー推計がない", prototypes["MAINTAIN"].summary_ja)
        self.assertIn("今すぐ確定しない", prototypes["START_SMALL"].summary_ja)
        self.assertIn("比較上不利でない", prototypes["COMPLETE_NOW"].summary_ja)
        self.assertIn("減らない", prototypes["REASSESS"].summary_ja)

    def test_prints_all_reviewable_candidates_only_when_requested(self) -> None:
        if os.getenv("PRINT_STEP_FOUR_DECISION_PROTOTYPE") != "1":
            self.skipTest("Set PRINT_STEP_FOUR_DECISION_PROTOTYPE=1 to print the text prototype.")
        for key, evidence in _all_evidence().items():
            policy = build_adaptive_pathway_position(evidence)
            prototype = _prototype_for(policy.overall_position)
            print(f"\n[{key}]")
            print("\n".join(_printable_lines(prototype)))


if __name__ == "__main__":
    unittest.main()

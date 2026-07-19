from __future__ import annotations

import unittest

from app.decision_policy import (
    ComparisonOption,
    DeclaredPriority,
    ThreeChoiceEvidence,
    build_adaptive_pathway_position,
    build_standard_economic_reading,
)


def _evidence(
    *,
    current_remaining: int = 30,
    first_remaining: int = 15,
    full_remaining: int = 0,
    first_annual: int = -46_552,
    full_annual: int = -93_105,
    first_upfront: int = 1_100_000,
    full_upfront: int = 2_200_000,
) -> ThreeChoiceEvidence:
    return ThreeChoiceEvidence(
        current=ComparisonOption(0, current_remaining, 0),
        first_phase=ComparisonOption(first_upfront, first_remaining, first_annual),
        full_coverage=ComparisonOption(full_upfront, full_remaining, full_annual),
    )


class StandardEconomicReadingTest(unittest.TestCase):
    def test_both_additional_options_not_supported_keeps_current_and_partial_in_focus(self) -> None:
        result = build_standard_economic_reading(_evidence())

        self.assertEqual(result.economic_reading, "additional_options_not_economically_supported")
        self.assertEqual(result.comparison_focus, "current_and_first_phase")
        self.assertEqual(
            result.basis,
            (
                "first_phase_annual_comparison_negative",
                "full_coverage_annual_comparison_negative",
                "first_phase_reduces_uncovered",
                "full_coverage_has_greater_annual_burden",
            ),
        )
        self.assertEqual(
            result.not_proven,
            ("investment_profitability", "physical_cooling_sufficiency"),
        )
        self.assertEqual(result.current_selected_position, "economic_baseline")
        self.assertEqual(
            result.first_phase_selected_position,
            "partial_coverage_beyond_economic_screen",
        )
        self.assertEqual(
            result.full_coverage_selected_position,
            "full_coverage_beyond_economic_screen",
        )
        self.assertTrue(result.decision_still_belongs_to_user)

    def test_only_first_phase_supported_keeps_full_coverage_out_of_the_economic_focus(self) -> None:
        result = build_standard_economic_reading(
            _evidence(first_annual=12_000, full_annual=-8_000)
        )

        self.assertEqual(result.economic_reading, "first_phase_only_economically_supported")
        self.assertEqual(result.comparison_focus, "first_phase_and_full_coverage")
        self.assertIn("first_phase_annual_comparison_not_negative", result.basis)
        self.assertIn("full_coverage_annual_comparison_negative", result.basis)
        self.assertEqual(result.first_phase_selected_position, "economically_supported")
        self.assertEqual(
            result.full_coverage_selected_position,
            "full_coverage_beyond_economic_screen",
        )

    def test_both_additional_options_supported_keeps_their_tradeoff_visible(self) -> None:
        result = build_standard_economic_reading(
            _evidence(first_annual=12_000, full_annual=20_000)
        )

        self.assertEqual(result.economic_reading, "additional_options_economically_supported")
        self.assertEqual(result.comparison_focus, "first_phase_and_full_coverage")
        self.assertIn("first_phase_annual_comparison_not_negative", result.basis)
        self.assertIn("full_coverage_annual_comparison_not_negative", result.basis)
        self.assertEqual(result.first_phase_selected_position, "economically_supported")
        self.assertEqual(result.full_coverage_selected_position, "economically_supported")

    def test_no_remaining_uncovered_means_no_additional_coverage_comparison(self) -> None:
        result = build_standard_economic_reading(
            _evidence(current_remaining=0, first_remaining=0, full_remaining=0)
        )

        self.assertEqual(result.economic_reading, "coverage_already_complete")
        self.assertEqual(result.comparison_focus, "current_only")
        self.assertEqual(result.basis, ("current_uncovered_is_zero",))

    def test_full_coverage_dominance_is_stated_as_a_fact_not_a_recommendation(self) -> None:
        result = build_standard_economic_reading(
            _evidence(
                first_remaining=15,
                full_remaining=0,
                first_annual=12_000,
                full_annual=20_000,
                first_upfront=2_200_000,
                full_upfront=2_200_000,
            )
        )

        self.assertEqual(result.economic_reading, "full_coverage_dominates_first_phase")
        self.assertEqual(result.comparison_focus, "full_coverage")
        self.assertIn("full_coverage_dominates_first_phase", result.basis)
        self.assertTrue(result.decision_still_belongs_to_user)

    def test_declared_priority_is_preserved_without_turning_into_a_recommendation(self) -> None:
        result = build_standard_economic_reading(
            _evidence(), declared_priority=DeclaredPriority.AVOID_UNCOVERED_COWS
        )

        self.assertEqual(result.declared_priority, DeclaredPriority.AVOID_UNCOVERED_COWS)
        self.assertEqual(result.priority_alignment, "coverage_priority_declared")
        self.assertNotIn("recommended", result.economic_reading)


class AdaptivePathwayPositionTest(unittest.TestCase):
    def test_standard_case_starts_small_and_keeps_the_economic_guardrail_visible(self) -> None:
        result = build_adaptive_pathway_position(_evidence())

        self.assertEqual(result.overall_position, "START_SMALL")
        self.assertEqual(result.uncovered_change, "partial_reduction")
        self.assertEqual(result.path_flexibility, "high")
        self.assertEqual(
            result.economic_guardrail,
            "first_phase_annual_comparison_negative",
        )
        self.assertEqual(
            result.basis,
            (
                "first_phase_reduces_uncovered",
                "full_coverage_reduces_uncovered_further",
                "first_phase_annual_comparison_negative",
            ),
        )
        self.assertEqual(
            result.not_proven,
            ("physical_cooling_sufficiency", "investment_profitability"),
        )
        self.assertTrue(result.decision_still_belongs_to_user)

    def test_no_uncovered_estimate_means_maintain_not_new_equipment(self) -> None:
        result = build_adaptive_pathway_position(
            _evidence(current_remaining=0, first_remaining=0, full_remaining=0)
        )

        self.assertEqual(result.overall_position, "MAINTAIN")
        self.assertEqual(result.uncovered_change, "already_covered")
        self.assertEqual(result.path_flexibility, "not_needed")
        self.assertEqual(result.economic_guardrail, "not_applicable")

    def test_full_coverage_is_complete_now_only_when_it_dominates_small_start(self) -> None:
        result = build_adaptive_pathway_position(
            _evidence(
                first_remaining=15,
                full_remaining=0,
                first_annual=12_000,
                full_annual=20_000,
                first_upfront=2_200_000,
                full_upfront=2_200_000,
            )
        )

        self.assertEqual(result.overall_position, "COMPLETE_NOW")
        self.assertEqual(result.uncovered_change, "complete_reduction")
        self.assertEqual(result.path_flexibility, "not_needed")
        self.assertEqual(result.economic_guardrail, "full_coverage_annual_comparison_not_negative")
        self.assertIn("full_coverage_dominates_first_phase", result.basis)

    def test_reassess_when_small_start_does_not_reduce_the_uncovered_estimate(self) -> None:
        result = build_adaptive_pathway_position(
            _evidence(first_remaining=30, full_remaining=0)
        )

        self.assertEqual(result.overall_position, "REASSESS")
        self.assertEqual(result.uncovered_change, "no_reduction_from_first_phase")
        self.assertEqual(result.path_flexibility, "unclear")
        self.assertEqual(result.economic_guardrail, "first_phase_annual_comparison_negative")
        self.assertIn("first_phase_does_not_reduce_uncovered", result.basis)


if __name__ == "__main__":
    unittest.main()

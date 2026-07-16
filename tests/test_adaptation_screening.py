from __future__ import annotations

import unittest

from app.adaptation_screening import (
    AdaptationInputError,
    TwoHorizonInput,
    build_two_horizon_screening,
)


class TwoHorizonScreeningTest(unittest.TestCase):
    def test_reduction_demo_keeps_current_and_future_gaps_separate(self) -> None:
        result = build_two_horizon_screening(
            TwoHorizonInput(
                current_target_cow_count=60,
                future_target_cow_count=45,
                existing_fan_count=10,
                first_phase_additional_fan_count=5,
                horizon_years=5,
            )
        )

        self.assertEqual(result.current_before.guideline_fan_count, 20)
        self.assertEqual(result.current_before.guideline_gap_fan_count, 10)
        self.assertEqual(result.current_after.guideline_gap_fan_count, 5)
        self.assertEqual(result.current_after.estimated_uncovered_cow_count, 15)
        self.assertEqual(result.future_after.guideline_fan_count, 15)
        self.assertEqual(result.future_after.guideline_gap_fan_count, 0)
        self.assertEqual(result.future_after.estimated_uncovered_cow_count, 0)
        self.assertTrue(result.transition_has_guideline_gap)
        self.assertEqual(result.herd_direction, "decrease")
        self.assertEqual(result.next_check_key, "cow_level_wind_speed")

    def test_maintaining_or_increasing_the_herd_changes_only_future_state(self) -> None:
        maintain = build_two_horizon_screening(
            TwoHorizonInput(60, 60, 10, 5, 5)
        )
        increase = build_two_horizon_screening(
            TwoHorizonInput(60, 75, 10, 5, 5)
        )

        self.assertEqual(maintain.current_after, increase.current_after)
        self.assertEqual(maintain.future_after.guideline_gap_fan_count, 5)
        self.assertEqual(increase.future_after.guideline_gap_fan_count, 10)
        self.assertEqual(maintain.herd_direction, "maintain")
        self.assertEqual(increase.herd_direction, "increase")

    def test_missing_future_count_is_a_formal_unconfirmed_branch(self) -> None:
        result = build_two_horizon_screening(
            TwoHorizonInput(60, None, 10, 5, 5)
        )

        self.assertIsNone(result.future_after)
        self.assertIsNone(result.herd_direction)
        self.assertEqual(result.next_check_key, "future_target_cow_count")

    def test_confirmed_coverage_replaces_guidance_denominator(self) -> None:
        guidance = build_two_horizon_screening(
            TwoHorizonInput(60, 45, 10, 5, 5)
        )
        confirmed = build_two_horizon_screening(
            TwoHorizonInput(60, 45, 10, 5, 5, confirmed_covered_cow_count=12)
        )

        self.assertEqual(guidance.coverage_status, "guidance_estimate")
        self.assertEqual(guidance.covered_cow_count_for_finance, 15)
        self.assertEqual(confirmed.coverage_status, "confirmed_measurement")
        self.assertEqual(confirmed.covered_cow_count_for_finance, 12)
        self.assertEqual(confirmed.next_check_key, "summer_milk_difference")

    def test_confirmed_coverage_cannot_exceed_headcount_guidance_capacity(self) -> None:
        with self.assertRaisesRegex(AdaptationInputError, "確認できたカバー頭数"):
            build_two_horizon_screening(
                TwoHorizonInput(60, 45, 10, 5, 5, confirmed_covered_cow_count=16)
            )


if __name__ == "__main__":
    unittest.main()

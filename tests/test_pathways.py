from __future__ import annotations

import unittest

from app.navigator import BarnInput, InputValidationError
from app.pathways import build_path_comparison


class PathwayComparisonTest(unittest.TestCase):
    def test_default_five_year_paths_start_from_the_same_current_state(self) -> None:
        result = build_path_comparison(BarnInput(60, 2, 10))

        self.assertEqual((result.start_year, result.end_year), (2026, 2030))
        self.assertEqual(tuple(path.key for path in result.paths), ("current", "first_phase", "full_coverage"))

        current, first_phase, full_coverage = result.paths
        self.assertEqual([year.uncovered_cow_count for year in current.years], [30, 30, 30, 30, 30])
        self.assertEqual([year.uncovered_cow_count for year in first_phase.years], [15, 15, 15, 15, 15])
        self.assertEqual([year.uncovered_cow_count for year in full_coverage.years], [0, 0, 0, 0, 0])
        self.assertEqual(current.cumulative_uncovered_cow_years, 150)
        self.assertEqual(first_phase.cumulative_uncovered_cow_years, 75)
        self.assertEqual(full_coverage.cumulative_uncovered_cow_years, 0)

    def test_later_investment_keeps_current_state_until_the_selected_year(self) -> None:
        result = build_path_comparison(BarnInput(60, 2, 10), investment_year=2028)
        first_phase = result.paths[1]
        full_coverage = result.paths[2]

        self.assertEqual([year.active_fan_count for year in first_phase.years], [10, 10, 15, 15, 15])
        self.assertEqual([year.investment_fan_count for year in first_phase.years], [0, 0, 5, 0, 0])
        self.assertEqual([year.uncovered_cow_count for year in first_phase.years], [30, 30, 15, 15, 15])
        self.assertEqual(first_phase.cumulative_uncovered_cow_years, 105)

        self.assertEqual([year.uncovered_cow_count for year in full_coverage.years], [30, 30, 0, 0, 0])
        self.assertEqual(full_coverage.cumulative_uncovered_cow_years, 60)

    def test_first_phase_requires_observation_and_does_not_add_the_second_phase(self) -> None:
        result = build_path_comparison(BarnInput(60, 2, 10), investment_year=2026)
        first_phase = result.paths[1]

        self.assertEqual(first_phase.review_year, 2027)
        self.assertEqual(first_phase.next_decision_status, "pending_observation")
        self.assertEqual(
            first_phase.monitoring_items,
            ("cow_level_wind_speed", "uncovered_stalls", "summer_milk_difference"),
        )
        self.assertTrue(all(year.active_fan_count == 15 for year in first_phase.years))
        self.assertTrue(all(year.additional_fan_count == 5 for year in first_phase.years))

    def test_custom_first_phase_count_is_used_in_every_post_investment_year(self) -> None:
        result = build_path_comparison(BarnInput(60, 2, 10, first_phase_fan_count=3))
        first_phase = result.paths[1]

        self.assertTrue(all(year.active_fan_count == 13 for year in first_phase.years))
        self.assertTrue(all(year.uncovered_cow_count == 21 for year in first_phase.years))
        self.assertEqual(first_phase.cumulative_uncovered_cow_years, 105)

    def test_no_shortage_creates_no_investment_event_or_pending_decision(self) -> None:
        result = build_path_comparison(BarnInput(60, 2, 20))

        for path in result.paths:
            self.assertIsNone(path.investment_year)
            self.assertIsNone(path.review_year)
            self.assertEqual(path.next_decision_status, "comparison_only")
            self.assertEqual(path.cumulative_uncovered_cow_years, 0)
            self.assertTrue(all(year.investment_fan_count == 0 for year in path.years))

    def test_investment_year_must_be_inside_the_comparison_period(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "投資年"):
            build_path_comparison(BarnInput(60, 2, 10), investment_year=2031)

    def test_comparison_period_must_be_between_one_and_fifteen_years(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "比較期間"):
            build_path_comparison(BarnInput(60, 2, 10), planning_horizon_years=0)


if __name__ == "__main__":
    unittest.main()

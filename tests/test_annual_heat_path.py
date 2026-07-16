from __future__ import annotations

from decimal import Decimal
import unittest

from app.annual_heat_path import (
    AnnualHeatPathInput,
    AnnualHeatPathInputError,
    calculate_annual_heat_path,
)


class AnnualHeatPathTest(unittest.TestCase):
    def test_compares_remaining_heat_loss_and_project_burden_with_no_action(self) -> None:
        result = calculate_annual_heat_path(
            AnnualHeatPathInput(
                initial_uncovered_cow_count=30,
                newly_covered_cow_count=15,
                heat_days_per_year=Decimal("100"),
                milk_loss_kg_per_cow_day=Decimal("3"),
                milk_price_yen_per_kg=Decimal("150"),
                variable_cost_ratio=Decimal("0.60"),
                annual_project_burden_yen=Decimal("300000"),
            )
        )

        self.assertEqual(result.remaining_uncovered_cow_count, 15)
        self.assertEqual(result.no_action_milk_loss_kg, Decimal("9000"))
        self.assertEqual(result.remaining_milk_loss_kg, Decimal("4500"))
        self.assertEqual(result.remaining_gross_milk_loss_yen, Decimal("675000"))
        self.assertEqual(result.no_action_contribution_loss_yen, Decimal("540000"))
        self.assertEqual(result.annual_total_adverse_impact_yen, Decimal("570000"))
        self.assertEqual(result.improvement_vs_no_action_yen, Decimal("-30000"))

    def test_a_larger_confirmed_milk_loss_can_make_the_action_an_improvement(self) -> None:
        result = calculate_annual_heat_path(
            AnnualHeatPathInput(
                initial_uncovered_cow_count=30,
                newly_covered_cow_count=15,
                heat_days_per_year=Decimal("100"),
                milk_loss_kg_per_cow_day=Decimal("4"),
                milk_price_yen_per_kg=Decimal("150"),
                variable_cost_ratio=Decimal("0.60"),
                annual_project_burden_yen=Decimal("300000"),
            )
        )

        self.assertEqual(result.improvement_vs_no_action_yen, Decimal("60000"))

    def test_no_action_is_the_zero_difference_baseline(self) -> None:
        result = calculate_annual_heat_path(
            AnnualHeatPathInput(
                initial_uncovered_cow_count=30,
                newly_covered_cow_count=0,
                heat_days_per_year=Decimal("100"),
                milk_loss_kg_per_cow_day=Decimal("3"),
                milk_price_yen_per_kg=Decimal("150"),
                variable_cost_ratio=Decimal("0.60"),
                annual_project_burden_yen=Decimal("0"),
            )
        )

        self.assertEqual(result.remaining_uncovered_cow_count, 30)
        self.assertEqual(result.improvement_vs_no_action_yen, Decimal("0"))

    def test_rejects_more_new_coverage_than_the_initial_uncovered_count(self) -> None:
        with self.assertRaises(AnnualHeatPathInputError):
            calculate_annual_heat_path(
                AnnualHeatPathInput(
                    initial_uncovered_cow_count=10,
                    newly_covered_cow_count=11,
                    heat_days_per_year=Decimal("100"),
                    milk_loss_kg_per_cow_day=Decimal("3"),
                    milk_price_yen_per_kg=Decimal("150"),
                    variable_cost_ratio=Decimal("0.60"),
                    annual_project_burden_yen=Decimal("0"),
                )
            )


if __name__ == "__main__":
    unittest.main()

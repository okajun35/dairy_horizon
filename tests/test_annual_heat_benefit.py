from __future__ import annotations

from decimal import Decimal
import unittest

from app.annual_heat_benefit import (
    AnnualHeatBenefitInput,
    AnnualHeatBenefitInputError,
    calculate_annual_heat_benefit,
)


class AnnualHeatBenefitTest(unittest.TestCase):
    def test_connects_covered_cows_and_heat_days_to_annual_milk_value(self) -> None:
        result = calculate_annual_heat_benefit(
            AnnualHeatBenefitInput(
                newly_covered_cow_count=15,
                heat_days_per_year=Decimal("97.25"),
                avoided_milk_loss_kg_per_cow_day=Decimal("3.0"),
                milk_price_yen_per_kg=Decimal("135"),
                variable_cost_ratio=Decimal("0.60"),
            )
        )

        self.assertEqual(result.annual_avoided_milk_kg, Decimal("4376.250"))
        self.assertEqual(result.annual_gross_milk_value_yen, Decimal("590793.750"))
        self.assertEqual(
            result.annual_contribution_benefit_yen,
            Decimal("236317.5000"),
        )

    def test_zero_coverage_or_zero_milk_difference_produces_zero_benefit(self) -> None:
        base = dict(
            heat_days_per_year=Decimal("97.25"),
            milk_price_yen_per_kg=Decimal("135"),
            variable_cost_ratio=Decimal("0.60"),
        )

        no_coverage = calculate_annual_heat_benefit(
            AnnualHeatBenefitInput(
                newly_covered_cow_count=0,
                avoided_milk_loss_kg_per_cow_day=Decimal("3.0"),
                **base,
            )
        )
        no_difference = calculate_annual_heat_benefit(
            AnnualHeatBenefitInput(
                newly_covered_cow_count=15,
                avoided_milk_loss_kg_per_cow_day=Decimal("0"),
                **base,
            )
        )

        self.assertEqual(no_coverage.annual_contribution_benefit_yen, 0)
        self.assertEqual(no_difference.annual_contribution_benefit_yen, 0)

    def test_rejects_values_outside_explicit_unit_boundaries(self) -> None:
        valid = dict(
            newly_covered_cow_count=15,
            heat_days_per_year=Decimal("97.25"),
            avoided_milk_loss_kg_per_cow_day=Decimal("3.0"),
            milk_price_yen_per_kg=Decimal("135"),
            variable_cost_ratio=Decimal("0.60"),
        )
        invalid_cases = (
            {"newly_covered_cow_count": -1},
            {"heat_days_per_year": Decimal("366.1")},
            {"avoided_milk_loss_kg_per_cow_day": Decimal("-0.1")},
            {"milk_price_yen_per_kg": Decimal("-1")},
            {"variable_cost_ratio": Decimal("1")},
        )

        for changes in invalid_cases:
            with self.subTest(changes=changes):
                with self.assertRaises(AnnualHeatBenefitInputError):
                    calculate_annual_heat_benefit(
                        AnnualHeatBenefitInput(**(valid | changes))
                    )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest

from app.financial_screening import (
    FinancialPlan,
    STANDARD_FINANCIAL_ASSUMPTIONS,
)
from app.project_annual_economics import calculate_project_annual_economics


class ProjectAnnualEconomicsTest(unittest.TestCase):
    def test_combines_heat_benefit_and_annual_project_burden(self) -> None:
        result = calculate_project_annual_economics(
            FinancialPlan(additional_fan_count=5, newly_covered_cow_count=15),
            replace(
                STANDARD_FINANCIAL_ASSUMPTIONS,
                heat_days_per_year=Decimal("97.25"),
            ),
        )

        self.assertEqual(result.status, "calculable")
        self.assertEqual(result.annual_avoided_milk_kg, Decimal("4376.250"))
        self.assertEqual(
            result.annual_contribution_benefit_yen,
            Decimal("236317.5000"),
        )
        self.assertEqual(
            result.annual_electricity_cost_yen,
            Decimal("125727.000000"),
        )
        self.assertEqual(
            result.annualized_capex_yen,
            Decimal("157142.8571428571428571428571"),
        )
        self.assertEqual(
            result.annual_project_balance_yen,
            Decimal("-46552.3571428571428571428571"),
        )

    def test_missing_milk_effect_keeps_costs_but_does_not_invent_benefit(self) -> None:
        result = calculate_project_annual_economics(
            FinancialPlan(additional_fan_count=5, newly_covered_cow_count=15),
            replace(
                STANDARD_FINANCIAL_ASSUMPTIONS,
                avoided_milk_loss_kg_per_cow_day=None,
            ),
        )

        self.assertEqual(result.status, "effect_unconfirmed")
        self.assertIsNone(result.annual_avoided_milk_kg)
        self.assertIsNone(result.annual_contribution_benefit_yen)
        self.assertIsNone(result.annual_project_balance_yen)
        self.assertGreater(result.annual_electricity_cost_yen, 0)

    def test_no_investment_is_not_reported_as_positive_balance(self) -> None:
        result = calculate_project_annual_economics(
            FinancialPlan(additional_fan_count=0, newly_covered_cow_count=0),
            STANDARD_FINANCIAL_ASSUMPTIONS,
        )

        self.assertEqual(result.status, "not_applicable")
        self.assertIsNone(result.annual_project_balance_yen)


if __name__ == "__main__":
    unittest.main()

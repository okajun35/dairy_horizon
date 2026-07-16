from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
import unittest

from app.financial_screening import (
    FinancialInputError,
    FinancialPlan,
    STANDARD_FINANCIAL_ASSUMPTIONS,
    calculate_financial_screening,
)


def _rounded(value: Decimal | None, places: str) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


class FinancialScreeningTest(unittest.TestCase):
    def test_zenrakuren_standard_example_reproduces_break_even_milk(self) -> None:
        result = calculate_financial_screening(
            FinancialPlan(additional_fan_count=1, newly_covered_cow_count=3),
            STANDARD_FINANCIAL_ASSUMPTIONS,
        )

        self.assertEqual(result.status, "calculable")
        self.assertEqual(result.incremental_capex_yen, Decimal("220000"))
        self.assertEqual(result.annual_energy_charge_yen, Decimal("23328.000"))
        self.assertEqual(result.annual_basic_charge_yen, Decimal("6240.0"))
        self.assertEqual(result.incremental_annual_electricity_cost_yen, Decimal("29568.000"))
        self.assertEqual(_rounded(result.annualized_capex_yen, "0.01"), Decimal("31428.57"))
        self.assertEqual(_rounded(result.break_even_sales_yen_per_cow_year, "0.01"), Decimal("50830.48"))
        self.assertEqual(_rounded(result.break_even_milk_kg_per_cow_year, "0.001"), Decimal("376.522"))
        self.assertEqual(_rounded(result.break_even_milk_kg_per_cow_day, "0.0001"), Decimal("3.1377"))

    def test_first_phase_uses_only_incremental_fans_and_newly_covered_cows(self) -> None:
        result = calculate_financial_screening(
            FinancialPlan(additional_fan_count=5, newly_covered_cow_count=15),
            STANDARD_FINANCIAL_ASSUMPTIONS,
        )

        self.assertEqual(result.incremental_capex_yen, Decimal("1100000"))
        self.assertEqual(result.incremental_annual_electricity_cost_yen, Decimal("147840.000"))
        self.assertEqual(_rounded(result.break_even_milk_kg_per_cow_day, "0.0001"), Decimal("3.1377"))
        self.assertEqual(result.maximum_affordable_capex_yen, Decimal("1006320.0000"))
        self.assertEqual(result.investment_margin_yen, Decimal("-93680.0000"))

    def test_higher_electricity_price_increases_cost_and_required_milk(self) -> None:
        plan = FinancialPlan(additional_fan_count=5, newly_covered_cow_count=15)
        current = calculate_financial_screening(plan, STANDARD_FINANCIAL_ASSUMPTIONS)
        higher_price = calculate_financial_screening(
            plan,
            replace(
                STANDARD_FINANCIAL_ASSUMPTIONS,
                electricity_price_yen_per_kwh=Decimal("28.35"),
            ),
        )

        self.assertGreater(
            higher_price.incremental_annual_electricity_cost_yen,
            current.incremental_annual_electricity_cost_yen,
        )
        self.assertEqual(
            higher_price.annual_energy_charge_yen,
            Decimal("122472.00000"),
        )
        self.assertEqual(
            higher_price.incremental_annual_electricity_cost_yen,
            Decimal("153672.00000"),
        )
        self.assertGreater(
            higher_price.break_even_milk_kg_per_cow_day,
            current.break_even_milk_kg_per_cow_day,
        )
        self.assertLess(
            higher_price.maximum_affordable_capex_yen,
            current.maximum_affordable_capex_yen,
        )

    def test_higher_milk_price_lowers_required_milk_volume(self) -> None:
        plan = FinancialPlan(additional_fan_count=5, newly_covered_cow_count=15)
        current = calculate_financial_screening(plan, STANDARD_FINANCIAL_ASSUMPTIONS)
        higher_price = calculate_financial_screening(
            plan,
            replace(
                STANDARD_FINANCIAL_ASSUMPTIONS,
                milk_price_yen_per_kg=Decimal("150"),
            ),
        )

        self.assertLess(
            higher_price.break_even_milk_kg_per_cow_day,
            current.break_even_milk_kg_per_cow_day,
        )

    def test_zero_milk_price_is_recovery_impossible_without_division_error(self) -> None:
        result = calculate_financial_screening(
            FinancialPlan(additional_fan_count=5, newly_covered_cow_count=15),
            replace(
                STANDARD_FINANCIAL_ASSUMPTIONS,
                milk_price_yen_per_kg=Decimal("0"),
            ),
        )

        self.assertEqual(result.status, "recovery_impossible")
        self.assertEqual(result.reason, "zero_milk_price")
        self.assertIsNone(result.break_even_milk_kg_per_cow_day)

    def test_zero_operating_hours_keeps_basic_charge_without_claiming_recovery(self) -> None:
        result = calculate_financial_screening(
            FinancialPlan(additional_fan_count=5, newly_covered_cow_count=15),
            replace(
                STANDARD_FINANCIAL_ASSUMPTIONS,
                operating_hours_per_day=Decimal("0"),
            ),
        )

        self.assertEqual(result.status, "recovery_impossible")
        self.assertEqual(result.reason, "zero_operating_hours")
        self.assertEqual(result.annual_energy_charge_yen, Decimal("0.000"))
        self.assertEqual(result.annual_basic_charge_yen, Decimal("31200.0"))
        self.assertEqual(
            result.incremental_annual_electricity_cost_yen, Decimal("31200.000")
        )
        self.assertIsNone(result.break_even_milk_kg_per_cow_day)
        self.assertEqual(result.maximum_affordable_capex_yen, Decimal("0"))
        self.assertIsNone(result.investment_margin_yen)

    def test_no_investment_is_not_reported_as_success(self) -> None:
        result = calculate_financial_screening(
            FinancialPlan(additional_fan_count=0, newly_covered_cow_count=0),
            STANDARD_FINANCIAL_ASSUMPTIONS,
        )

        self.assertEqual(result.status, "not_applicable")
        self.assertEqual(result.reason, "no_investment")
        self.assertEqual(result.incremental_capex_yen, Decimal("0"))
        self.assertEqual(result.incremental_annual_electricity_cost_yen, Decimal("0"))
        self.assertIsNone(result.break_even_milk_kg_per_cow_day)
        self.assertIsNone(result.maximum_affordable_capex_yen)

    def test_investment_without_covered_cows_cannot_calculate_recovery(self) -> None:
        result = calculate_financial_screening(
            FinancialPlan(additional_fan_count=1, newly_covered_cow_count=0),
            STANDARD_FINANCIAL_ASSUMPTIONS,
        )

        self.assertEqual(result.status, "recovery_impossible")
        self.assertEqual(result.reason, "zero_covered_cows")
        self.assertIsNone(result.break_even_milk_kg_per_cow_day)

    def test_invalid_assumptions_are_rejected(self) -> None:
        invalid_cases = (
            replace(STANDARD_FINANCIAL_ASSUMPTIONS, useful_life_years=0),
            replace(STANDARD_FINANCIAL_ASSUMPTIONS, variable_cost_ratio=Decimal("1")),
            replace(STANDARD_FINANCIAL_ASSUMPTIONS, operating_hours_per_day=Decimal("25")),
            replace(STANDARD_FINANCIAL_ASSUMPTIONS, heat_days_per_year=Decimal("367")),
            replace(STANDARD_FINANCIAL_ASSUMPTIONS, inverter_reduction_ratio=Decimal("1.01")),
            replace(STANDARD_FINANCIAL_ASSUMPTIONS, tax_basis="tax_inclusive"),  # type: ignore[arg-type]
        )
        for assumptions in invalid_cases:
            with self.subTest(assumptions=assumptions):
                with self.assertRaises(FinancialInputError):
                    calculate_financial_screening(
                        FinancialPlan(additional_fan_count=1, newly_covered_cow_count=3),
                        assumptions,
                    )


if __name__ == "__main__":
    unittest.main()

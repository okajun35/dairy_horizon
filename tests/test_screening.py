from __future__ import annotations

from decimal import Decimal
from dataclasses import replace
import unittest

from app.screening import (
    ClimateYear,
    ScreeningAssumptions,
    ScreeningInput,
    build_screening,
)


def assumptions() -> ScreeningAssumptions:
    return ScreeningAssumptions(
        cows_per_fan=3,
        installed_cost_yen_per_unit_excl_tax=Decimal("220000"),
        electricity_price_yen_per_kwh=Decimal("27"),
        power_kw_per_unit=Decimal("0.4"),
        operating_hours_per_day=Decimal("24"),
        basic_charge_yen_per_kw_month=Decimal("1300"),
        inverter_reduction_ratio=Decimal("0.25"),
        useful_life_years=7,
        variable_cost_ratio=Decimal("0.60"),
        consumption_tax_ratio=Decimal("0.10"),
        annual_interest_rate=Decimal("0"),
        capital_repayment_years=7,
        max_uncovered_cow_heat_days=Decimal("3200"),
        avoided_milk_loss_cases=(Decimal("2"), Decimal("3"), Decimal("4")),
    )


def climate() -> tuple[ClimateYear, ...]:
    return tuple(
        ClimateYear(year=2026 + index, heat_stress_days=Decimal(str(days)))
        for index, days in enumerate((90, 95, 100, 105, 110, 115, 120, 125, 130, 135, 140, 145, 150, 155, 160, 165, 170, 175, 180, 185))
    )


class ScreeningTest(unittest.TestCase):
    def test_screening_compares_now_recommended_and_later_without_financial_detail_inputs(self) -> None:
        result = build_screening(
            ScreeningInput(lactating_cows=60, lane_count=2, existing_fan_count=10, milk_price_yen_per_kg=Decimal("135"), target_years=5),
            assumptions(), climate(),
        )
        self.assertEqual(("now", "recommended", "later"), tuple(item.key for item in result.timing_options))
        self.assertEqual(5, result.target_years)
        self.assertEqual(6, len(result.standard_assumption_labels_ja))

    def test_each_timing_option_exposes_three_cases_and_tax_exclusive_plus_cash_required(self) -> None:
        result = build_screening(
            ScreeningInput(lactating_cows=60, lane_count=2, existing_fan_count=10, milk_price_yen_per_kg=Decimal("135"), target_years=5),
            assumptions(), climate(),
        )
        option = result.timing_options[0]
        self.assertEqual(("cautious", "standard", "improved"), tuple(case.key for case in option.cases))
        self.assertEqual(option.total_capex_yen_excl_tax * Decimal("1.10"), option.cash_required_yen_incl_tax)

    def test_target_years_up_to_twenty_are_supported(self) -> None:
        result = build_screening(
            ScreeningInput(lactating_cows=60, lane_count=2, existing_fan_count=10, milk_price_yen_per_kg=Decimal("135"), target_years=20),
            assumptions(), climate(),
        )
        self.assertEqual(2045, result.target_end_year)

    def test_safe_target_period_recommends_no_new_investment_instead_of_a_fictional_date(self) -> None:
        safe_climate = tuple(ClimateYear(year=2026 + index, heat_stress_days=Decimal("50")) for index in range(20))
        result = build_screening(
            ScreeningInput(lactating_cows=60, lane_count=2, existing_fan_count=10, milk_price_yen_per_kg=Decimal("135"), target_years=5),
            assumptions(), safe_climate,
        )
        recommended = result.timing_options[1]
        self.assertEqual("追加投資なし", recommended.action_summary_ja)
        self.assertTrue(all(case.passes_target for case in recommended.cases))

    def test_boundary_case_asks_for_the_most_valuable_next_information(self) -> None:
        result = build_screening(
            ScreeningInput(lactating_cows=60, lane_count=2, existing_fan_count=10, milk_price_yen_per_kg=Decimal("135"), target_years=5),
            assumptions(), climate(),
        )
        self.assertIn(result.next_question.kind, {"quote", "milk_loss", "milk_price"})
        self.assertTrue(result.next_question.question_ja)
        self.assertTrue(result.next_question.action_ja)

    def test_detailed_interest_setting_changes_screening_affordability(self) -> None:
        request = ScreeningInput(lactating_cows=60, lane_count=2, existing_fan_count=10, milk_price_yen_per_kg=Decimal("135"), target_years=5)
        standard = build_screening(request, assumptions(), climate())
        detailed = build_screening(request, replace(assumptions(), annual_interest_rate=Decimal("0.08"), capital_repayment_years=7), climate())
        self.assertLess(
            detailed.timing_options[0].cases[1].maximum_affordable_capex_yen,
            standard.timing_options[0].cases[1].maximum_affordable_capex_yen,
        )


if __name__ == "__main__":
    unittest.main()

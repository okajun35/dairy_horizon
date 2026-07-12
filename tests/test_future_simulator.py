from __future__ import annotations

from decimal import Decimal
import unittest

from app.future_simulator import (
    FutureFarmInputs,
    InvestmentTiming,
    YearConditions,
    recommend_timing,
    simulate_future,
)
from app.vertical_slice import build_dashboard


def inputs() -> FutureFarmInputs:
    return FutureFarmInputs(
        total_cows=60,
        target_fan_count=20,
        existing_fan_count=10,
        cows_per_fan=3,
        stage_one_fan_count=5,
        full_installation_fan_count=5,
        installed_cost_yen_per_unit=Decimal("220000"),
        power_kw_per_unit=Decimal("0.4"),
        operating_hours_per_day=Decimal("24"),
        basic_charge_yen_per_kw_month=Decimal("1300"),
        inverter_reduction_ratio=Decimal("0.25"),
        useful_life_years=7,
        existing_fans_service_until_year=2032,
        avoided_milk_loss_kg_per_cow_day=Decimal("3"),
        variable_cost_ratio=Decimal("0.60"),
        annual_cash_before_heat_yen=Decimal("1600000"),
        starting_cash_reserve_yen=Decimal("1000000"),
        maximum_debt_yen=Decimal("2500000"),
        minimum_annual_cash_yen=Decimal("0"),
        maximum_uncovered_cow_heat_days=Decimal("3200"),
    )


def years() -> tuple[YearConditions, ...]:
    return tuple(
        YearConditions(
            year=year,
            heat_stress_days=Decimal(str(days)),
            milk_price_yen_per_kg=Decimal("135"),
            electricity_price_yen_per_kwh=Decimal("27"),
        )
        for year, days in ((2026, 90), (2027, 95), (2028, 100), (2029, 105), (2030, 110), (2031, 115), (2032, 120), (2033, 125), (2034, 130))
    )


class FutureSimulatorTest(unittest.TestCase):
    def test_current_operation_ends_at_first_heat_exposure_failure(self) -> None:
        result = simulate_future(inputs(), years(), InvestmentTiming())
        self.assertEqual(4, result.choice_horizon_years)
        self.assertEqual(2030, result.first_failing_year)
        self.assertEqual("heat_exposure_limit", result.first_failing_condition)

    def test_investment_timing_extends_horizon_and_records_capex_once(self) -> None:
        result = simulate_future(inputs(), years(), InvestmentTiming(stage_one_year=2026, full_installation_year=2027))
        self.assertGreater(result.choice_horizon_years, 4)
        self.assertEqual(Decimal("1100000"), result.years[0].investment_capex_yen)
        self.assertEqual(Decimal("1100000"), result.years[1].investment_capex_yen)
        self.assertEqual(20, result.years[1].active_fan_count)

    def test_worsening_heat_cannot_extend_choice_horizon(self) -> None:
        baseline = simulate_future(inputs(), years(), InvestmentTiming())
        hotter_years = tuple(
            YearConditions(
                year=item.year,
                heat_stress_days=item.heat_stress_days + Decimal("20"),
                milk_price_yen_per_kg=item.milk_price_yen_per_kg,
                electricity_price_yen_per_kwh=item.electricity_price_yen_per_kwh,
            )
            for item in years()
        )
        hotter = simulate_future(inputs(), hotter_years, InvestmentTiming())
        self.assertLessEqual(hotter.choice_horizon_years, baseline.choice_horizon_years)

    def test_debt_constraint_is_the_first_failure_when_capex_exceeds_limit(self) -> None:
        constrained = FutureFarmInputs(**(inputs().__dict__ | {"starting_cash_reserve_yen": Decimal("0"), "maximum_debt_yen": Decimal("100000")}))
        result = simulate_future(constrained, years(), InvestmentTiming(full_installation_year=2026))
        self.assertEqual(0, result.choice_horizon_years)
        self.assertEqual(2026, result.first_failing_year)
        self.assertEqual("maximum_debt_exceeded", result.first_failing_condition)

    def test_recommendation_is_a_concrete_timing_with_a_horizon(self) -> None:
        recommendation = recommend_timing(inputs(), years())
        self.assertGreaterEqual(recommendation.choice_horizon_years, 4)
        self.assertTrue(recommendation.action_summary_ja)
        if recommendation.timing.stage_one_year and recommendation.timing.full_installation_year:
            self.assertLessEqual(recommendation.timing.stage_one_year, recommendation.timing.full_installation_year)

    def test_defaulted_financial_capacity_values_can_be_overridden(self) -> None:
        dashboard = build_dashboard({
            "full_installation_year": "2027",
            "starting_cash_reserve_yen": "0",
            "maximum_debt_yen": "100000",
        })
        self.assertEqual("0", dashboard["values"]["starting_cash_reserve_yen"])
        self.assertEqual("100000", dashboard["values"]["maximum_debt_yen"])
        self.assertEqual("maximum_debt_exceeded", dashboard["future_simulation"].first_failing_condition)


if __name__ == "__main__":
    unittest.main()

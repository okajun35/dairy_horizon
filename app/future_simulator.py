"""Deterministic annual farm and investment-timing scenario calculations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import product


ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class YearConditions:
    year: int
    heat_stress_days: Decimal
    milk_price_yen_per_kg: Decimal
    electricity_price_yen_per_kwh: Decimal


@dataclass(frozen=True)
class InvestmentTiming:
    stage_one_year: int | None = None
    full_installation_year: int | None = None


@dataclass(frozen=True)
class FutureFarmInputs:
    total_cows: int
    target_fan_count: int
    existing_fan_count: int
    cows_per_fan: int
    stage_one_fan_count: int
    full_installation_fan_count: int
    installed_cost_yen_per_unit: Decimal
    power_kw_per_unit: Decimal
    operating_hours_per_day: Decimal
    basic_charge_yen_per_kw_month: Decimal
    inverter_reduction_ratio: Decimal
    useful_life_years: int
    existing_fans_service_until_year: int
    avoided_milk_loss_kg_per_cow_day: Decimal
    variable_cost_ratio: Decimal
    annual_cash_before_heat_yen: Decimal
    starting_cash_reserve_yen: Decimal
    maximum_debt_yen: Decimal
    minimum_annual_cash_yen: Decimal
    maximum_uncovered_cow_heat_days: Decimal


@dataclass(frozen=True)
class SimulatedYear:
    year: int
    heat_stress_days: Decimal
    milk_price_yen_per_kg: Decimal
    electricity_price_yen_per_kwh: Decimal
    active_fan_count: int
    uncovered_cow_count: int
    uncovered_cow_heat_days: Decimal
    investment_capex_yen: Decimal
    annual_heat_loss_yen: Decimal
    annual_added_electricity_cost_yen: Decimal
    annual_cash_yen: Decimal
    cash_reserve_yen: Decimal
    debt_yen: Decimal
    passes: bool
    failing_condition: str | None


@dataclass(frozen=True)
class FutureSimulation:
    timing: InvestmentTiming
    years: tuple[SimulatedYear, ...]
    choice_horizon_years: int
    first_failing_year: int | None
    first_failing_condition: str | None
    total_investment_yen: Decimal


@dataclass(frozen=True)
class TimingRecommendation:
    timing: InvestmentTiming
    choice_horizon_years: int
    first_failing_year: int | None
    first_failing_condition: str | None
    total_investment_yen: Decimal
    action_summary_ja: str


class FutureScenarioValidationError(ValueError):
    """Raised when a future scenario has inconsistent timing or units."""


def _active_count(start_year: int | None, year: int, count: int, useful_life_years: int) -> int:
    if start_year is None or year < start_year:
        return 0
    return count if year < start_year + useful_life_years else 0


def _annual_added_electricity_cost(inputs: FutureFarmInputs, active_added_fans: int, conditions: YearConditions) -> Decimal:
    basic = Decimal(active_added_fans) * inputs.power_kw_per_unit * inputs.basic_charge_yen_per_kw_month * Decimal("12")
    energy = (
        Decimal(active_added_fans) * inputs.power_kw_per_unit * inputs.operating_hours_per_day
        * conditions.heat_stress_days * conditions.electricity_price_yen_per_kwh * (ONE - inputs.inverter_reduction_ratio)
    )
    return basic + energy


def _heat_loss(inputs: FutureFarmInputs, uncovered_cow_count: int, conditions: YearConditions) -> Decimal:
    return (
        Decimal(uncovered_cow_count) * inputs.avoided_milk_loss_kg_per_cow_day
        * conditions.heat_stress_days * conditions.milk_price_yen_per_kg * (ONE - inputs.variable_cost_ratio)
    )


def _validate(inputs: FutureFarmInputs, conditions: tuple[YearConditions, ...], timing: InvestmentTiming) -> None:
    if not conditions:
        raise FutureScenarioValidationError("at least one annual condition is required")
    years = [item.year for item in conditions]
    if years != sorted(years) or len(set(years)) != len(years):
        raise FutureScenarioValidationError("annual conditions must have unique ascending years")
    if inputs.target_fan_count < inputs.existing_fan_count:
        raise FutureScenarioValidationError("existing fans cannot exceed target fans")
    if inputs.cows_per_fan < 1 or inputs.useful_life_years < 1:
        raise FutureScenarioValidationError("fan capacity and useful life must be positive")
    if any(value < ZERO for value in (
        inputs.annual_cash_before_heat_yen, inputs.starting_cash_reserve_yen,
        inputs.maximum_debt_yen, inputs.minimum_annual_cash_yen,
        inputs.maximum_uncovered_cow_heat_days,
    )):
        raise FutureScenarioValidationError("cash, debt, and heat-exposure limits cannot be negative")
    if not ZERO <= inputs.variable_cost_ratio < ONE:
        raise FutureScenarioValidationError("variable cost ratio must be between zero and one")
    if timing.stage_one_year and timing.stage_one_year not in years:
        raise FutureScenarioValidationError("stage-one year must be in the simulated period")
    if timing.full_installation_year and timing.full_installation_year not in years:
        raise FutureScenarioValidationError("full-installation year must be in the simulated period")
    if timing.stage_one_year and timing.full_installation_year and timing.stage_one_year > timing.full_installation_year:
        raise FutureScenarioValidationError("stage one cannot follow full installation")


def simulate_future(
    inputs: FutureFarmInputs,
    conditions: tuple[YearConditions, ...],
    timing: InvestmentTiming,
) -> FutureSimulation:
    """Simulate annual cash, heat coverage, debt, and first failed constraint."""
    _validate(inputs, conditions, timing)
    cash_reserve = inputs.starting_cash_reserve_yen
    debt = ZERO
    result: list[SimulatedYear] = []
    total_investment = ZERO
    for annual in conditions:
        full_event_fans = (
            inputs.full_installation_fan_count
            if timing.stage_one_year is not None
            else inputs.full_installation_fan_count + inputs.stage_one_fan_count
        )
        event_fans = 0
        if annual.year == timing.stage_one_year:
            event_fans += inputs.stage_one_fan_count
        if annual.year == timing.full_installation_year:
            event_fans += full_event_fans
        capex = Decimal(event_fans) * inputs.installed_cost_yen_per_unit
        total_investment += capex
        cash_used = min(cash_reserve, capex)
        cash_reserve -= cash_used
        debt += capex - cash_used
        debt_after_investment = debt

        existing_active = inputs.existing_fan_count if annual.year <= inputs.existing_fans_service_until_year else 0
        stage_active = _active_count(timing.stage_one_year, annual.year, inputs.stage_one_fan_count, inputs.useful_life_years)
        full_active = _active_count(timing.full_installation_year, annual.year, full_event_fans, inputs.useful_life_years)
        active_fans = min(inputs.target_fan_count, existing_active + stage_active + full_active)
        uncovered_cows = max(0, inputs.total_cows - active_fans * inputs.cows_per_fan)
        exposure = Decimal(uncovered_cows) * annual.heat_stress_days
        heat_loss = _heat_loss(inputs, uncovered_cows, annual)
        electricity = _annual_added_electricity_cost(inputs, stage_active + full_active, annual)
        annual_cash = inputs.annual_cash_before_heat_yen - heat_loss - electricity

        if annual_cash > ZERO and debt > ZERO:
            repayment = min(annual_cash, debt)
            debt -= repayment
            cash_reserve += annual_cash - repayment
        else:
            cash_reserve += annual_cash

        failure = next(
            (
                name for name, failed in (
                    ("maximum_debt_exceeded", debt_after_investment > inputs.maximum_debt_yen),
                    ("minimum_annual_cash_not_met", annual_cash < inputs.minimum_annual_cash_yen),
                    ("heat_exposure_limit", exposure > inputs.maximum_uncovered_cow_heat_days),
                    ("cash_reserve_depleted", cash_reserve < ZERO),
                )
                if failed
            ),
            None,
        )
        result.append(SimulatedYear(
            year=annual.year, heat_stress_days=annual.heat_stress_days,
            milk_price_yen_per_kg=annual.milk_price_yen_per_kg,
            electricity_price_yen_per_kwh=annual.electricity_price_yen_per_kwh,
            active_fan_count=active_fans, uncovered_cow_count=uncovered_cows,
            uncovered_cow_heat_days=exposure, investment_capex_yen=capex,
            annual_heat_loss_yen=heat_loss, annual_added_electricity_cost_yen=electricity,
            annual_cash_yen=annual_cash, cash_reserve_yen=cash_reserve, debt_yen=debt,
            passes=failure is None, failing_condition=failure,
        ))

    first = next((item for item in result if not item.passes), None)
    horizon = next((index for index, item in enumerate(result) if not item.passes), len(result))
    return FutureSimulation(
        timing=timing, years=tuple(result), choice_horizon_years=horizon,
        first_failing_year=first.year if first else None,
        first_failing_condition=first.failing_condition if first else None,
        total_investment_yen=total_investment,
    )


def recommend_timing(inputs: FutureFarmInputs, conditions: tuple[YearConditions, ...]) -> TimingRecommendation:
    """Choose the longest-horizon practical timing from a small deterministic search."""
    years = tuple(item.year for item in conditions)
    candidates: list[FutureSimulation] = [simulate_future(inputs, conditions, InvestmentTiming())]
    options = (None,) + years
    for stage_year, full_year in product(options, options):
        if stage_year is None and full_year is None:
            continue
        if stage_year is not None and full_year is not None and stage_year > full_year:
            continue
        candidates.append(simulate_future(inputs, conditions, InvestmentTiming(stage_year, full_year)))
    def recommendation_key(item: FutureSimulation) -> tuple[int, Decimal, int, int]:
        action_count = int(item.timing.stage_one_year is not None) + int(item.timing.full_installation_year is not None)
        first_action_year = item.timing.stage_one_year or item.timing.full_installation_year or 9999
        return (item.choice_horizon_years, -item.total_investment_yen, -action_count, -first_action_year)

    selected = max(candidates, key=recommendation_key)
    actions: list[str] = []
    if selected.timing.stage_one_year:
        actions.append(f"{selected.timing.stage_one_year}年に第1期")
    if selected.timing.full_installation_year:
        actions.append(f"{selected.timing.full_installation_year}年に全数整備")
    summary = "、".join(actions) if actions else "追加投資なし"
    return TimingRecommendation(
        timing=selected.timing, choice_horizon_years=selected.choice_horizon_years,
        first_failing_year=selected.first_failing_year,
        first_failing_condition=selected.first_failing_condition,
        total_investment_yen=selected.total_investment_yen,
        action_summary_ja=summary,
    )

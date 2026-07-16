"""Deterministic incremental fan investment screening.

The formulas follow the simple Zenrakuren COW BELL No.178 example. Climate
data supplies heat days separately; it never changes the fan count here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


ZERO = Decimal("0")
ONE = Decimal("1")
MONTHS_PER_YEAR = Decimal("12")
STANDARD_USEFUL_LIFE_YEARS = 7
FinancialStatus = Literal["not_applicable", "calculable", "recovery_impossible"]
FinancialReason = Literal[
    "no_investment",
    "zero_milk_price",
    "zero_covered_cows",
    "zero_heat_days",
    "zero_operating_hours",
]


class FinancialInputError(ValueError):
    """Raised when a financial screening input is outside its valid unit range."""


@dataclass(frozen=True)
class FinancialPlan:
    additional_fan_count: int
    newly_covered_cow_count: int


@dataclass(frozen=True)
class FinancialAssumptions:
    tax_basis: Literal["tax_exclusive"]
    installed_cost_yen_per_fan: Decimal
    power_kw_per_fan: Decimal
    operating_hours_per_day: Decimal
    heat_days_per_year: Decimal
    electricity_price_yen_per_kwh: Decimal
    basic_charge_yen_per_kw_month: Decimal
    inverter_reduction_ratio: Decimal
    useful_life_years: int
    variable_cost_ratio: Decimal
    milk_price_yen_per_kg: Decimal
    avoided_milk_loss_kg_per_cow_day: Decimal | None


@dataclass(frozen=True)
class FinancialScreeningResult:
    status: FinancialStatus
    reason: FinancialReason | None
    incremental_capex_yen: Decimal
    annual_energy_charge_yen: Decimal
    annual_basic_charge_yen: Decimal
    incremental_annual_electricity_cost_yen: Decimal
    annualized_capex_yen: Decimal
    annual_burden_yen: Decimal
    break_even_sales_yen_per_cow_year: Decimal | None
    break_even_milk_kg_per_cow_year: Decimal | None
    break_even_milk_kg_per_cow_day: Decimal | None
    maximum_affordable_capex_yen: Decimal | None
    investment_margin_yen: Decimal | None


STANDARD_FINANCIAL_ASSUMPTIONS = FinancialAssumptions(
    tax_basis="tax_exclusive",
    installed_cost_yen_per_fan=Decimal("220000"),
    power_kw_per_fan=Decimal("0.4"),
    operating_hours_per_day=Decimal("24"),
    heat_days_per_year=Decimal("120"),
    electricity_price_yen_per_kwh=Decimal("27"),
    basic_charge_yen_per_kw_month=Decimal("1300"),
    inverter_reduction_ratio=Decimal("0.25"),
    useful_life_years=STANDARD_USEFUL_LIFE_YEARS,
    variable_cost_ratio=Decimal("0.60"),
    milk_price_yen_per_kg=Decimal("135"),
    avoided_milk_loss_kg_per_cow_day=Decimal("3.0"),
)


def _validate(plan: FinancialPlan, assumptions: FinancialAssumptions) -> None:
    if plan.additional_fan_count < 0:
        raise FinancialInputError("追加ファン数は0以上で入力してください。")
    if plan.newly_covered_cow_count < 0:
        raise FinancialInputError("新たにカバーする頭数は0以上で入力してください。")
    if assumptions.tax_basis != "tax_exclusive":
        raise FinancialInputError("標準計算は税抜金額で統一してください。")
    if assumptions.installed_cost_yen_per_fan < ZERO:
        raise FinancialInputError("1台あたり設備費は0円以上で入力してください。")
    if assumptions.power_kw_per_fan < ZERO:
        raise FinancialInputError("1台あたり消費電力は0kW以上で入力してください。")
    if not ZERO <= assumptions.operating_hours_per_day <= Decimal("24"):
        raise FinancialInputError("1日あたり運転時間は0〜24時間で入力してください。")
    if not ZERO <= assumptions.heat_days_per_year <= Decimal("366"):
        raise FinancialInputError("年間運転日数は0〜366日で入力してください。")
    if assumptions.electricity_price_yen_per_kwh < ZERO:
        raise FinancialInputError("電力量単価は0円/kWh以上で入力してください。")
    if assumptions.basic_charge_yen_per_kw_month < ZERO:
        raise FinancialInputError("基本料金単価は0円/kW・月以上で入力してください。")
    if not ZERO <= assumptions.inverter_reduction_ratio <= ONE:
        raise FinancialInputError("インバーター削減率は0〜1で入力してください。")
    if assumptions.useful_life_years < 1:
        raise FinancialInputError("耐用年数は1年以上で入力してください。")
    if not ZERO <= assumptions.variable_cost_ratio < ONE:
        raise FinancialInputError("変動費率は0以上1未満で入力してください。")
    if assumptions.milk_price_yen_per_kg < ZERO:
        raise FinancialInputError("乳価は0円/kg以上で入力してください。")
    if (
        assumptions.avoided_milk_loss_kg_per_cow_day is not None
        and assumptions.avoided_milk_loss_kg_per_cow_day < ZERO
    ):
        raise FinancialInputError("防げる乳量は0kg/頭・日以上で入力してください。")


def _empty_result(status: FinancialStatus, reason: FinancialReason) -> FinancialScreeningResult:
    return FinancialScreeningResult(
        status=status,
        reason=reason,
        incremental_capex_yen=ZERO,
        annual_energy_charge_yen=ZERO,
        annual_basic_charge_yen=ZERO,
        incremental_annual_electricity_cost_yen=ZERO,
        annualized_capex_yen=ZERO,
        annual_burden_yen=ZERO,
        break_even_sales_yen_per_cow_year=None,
        break_even_milk_kg_per_cow_year=None,
        break_even_milk_kg_per_cow_day=None,
        maximum_affordable_capex_yen=None,
        investment_margin_yen=None,
    )


def calculate_financial_screening(
    plan: FinancialPlan,
    assumptions: FinancialAssumptions,
) -> FinancialScreeningResult:
    """Calculate incremental capex, electricity, and break-even milk.

    The plan must contain only fans added by this option and cows newly
    covered by those fans. Existing equipment costs are deliberately excluded.
    """
    _validate(plan, assumptions)
    if plan.additional_fan_count == 0:
        return _empty_result("not_applicable", "no_investment")

    fan_count = Decimal(plan.additional_fan_count)
    covered_cows = Decimal(plan.newly_covered_cow_count)
    incremental_capex = fan_count * assumptions.installed_cost_yen_per_fan
    annual_energy = (
        fan_count
        * assumptions.power_kw_per_fan
        * assumptions.operating_hours_per_day
        * assumptions.heat_days_per_year
        * assumptions.electricity_price_yen_per_kwh
        * (ONE - assumptions.inverter_reduction_ratio)
    )
    annual_basic = (
        fan_count
        * assumptions.power_kw_per_fan
        * assumptions.basic_charge_yen_per_kw_month
        * MONTHS_PER_YEAR
    )
    annual_electricity = annual_energy + annual_basic
    annualized_capex = incremental_capex / Decimal(assumptions.useful_life_years)
    annual_burden = annualized_capex + annual_electricity

    impossible_reason: FinancialReason | None = None
    if assumptions.milk_price_yen_per_kg == ZERO:
        impossible_reason = "zero_milk_price"
    elif covered_cows == ZERO:
        impossible_reason = "zero_covered_cows"
    elif assumptions.heat_days_per_year == ZERO:
        impossible_reason = "zero_heat_days"
    elif assumptions.operating_hours_per_day == ZERO:
        impossible_reason = "zero_operating_hours"

    if impossible_reason is not None:
        return FinancialScreeningResult(
            status="recovery_impossible",
            reason=impossible_reason,
            incremental_capex_yen=incremental_capex,
            annual_energy_charge_yen=annual_energy,
            annual_basic_charge_yen=annual_basic,
            incremental_annual_electricity_cost_yen=annual_electricity,
            annualized_capex_yen=annualized_capex,
            annual_burden_yen=annual_burden,
            break_even_sales_yen_per_cow_year=None,
            break_even_milk_kg_per_cow_year=None,
            break_even_milk_kg_per_cow_day=None,
            maximum_affordable_capex_yen=ZERO,
            investment_margin_yen=None,
        )

    contribution_margin = ONE - assumptions.variable_cost_ratio
    break_even_sales_per_cow = annual_burden / contribution_margin / covered_cows
    break_even_milk_per_cow_year = (
        break_even_sales_per_cow / assumptions.milk_price_yen_per_kg
    )
    break_even_milk_per_cow_day = (
        break_even_milk_per_cow_year / assumptions.heat_days_per_year
    )

    maximum_affordable_capex: Decimal | None = None
    investment_margin: Decimal | None = None
    if assumptions.avoided_milk_loss_kg_per_cow_day is not None:
        annual_milk_contribution = (
            covered_cows
            * assumptions.heat_days_per_year
            * assumptions.avoided_milk_loss_kg_per_cow_day
            * assumptions.milk_price_yen_per_kg
            * contribution_margin
        )
        maximum_affordable_capex = max(
            ZERO,
            (annual_milk_contribution - annual_electricity)
            * Decimal(assumptions.useful_life_years),
        )
        investment_margin = maximum_affordable_capex - incremental_capex

    return FinancialScreeningResult(
        status="calculable",
        reason=None,
        incremental_capex_yen=incremental_capex,
        annual_energy_charge_yen=annual_energy,
        annual_basic_charge_yen=annual_basic,
        incremental_annual_electricity_cost_yen=annual_electricity,
        annualized_capex_yen=annualized_capex,
        annual_burden_yen=annual_burden,
        break_even_sales_yen_per_cow_year=break_even_sales_per_cow,
        break_even_milk_kg_per_cow_year=break_even_milk_per_cow_year,
        break_even_milk_kg_per_cow_day=break_even_milk_per_cow_day,
        maximum_affordable_capex_yen=maximum_affordable_capex,
        investment_margin_yen=investment_margin,
    )

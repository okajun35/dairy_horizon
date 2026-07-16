"""Small, explicit equipment branches for the staged-investment demo."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

from app.financial_screening import (
    FinancialAssumptions,
    FinancialPlan,
    calculate_financial_screening,
)


EquipmentKey = Literal["standard_100", "efficient_100", "large_high_airflow"]
EquipmentCoverageStatus = Literal[
    "guidance_estimate",
    "confirmed_measurement",
    "needs_measurement",
    "not_applicable",
]


@dataclass(frozen=True)
class EquipmentBranch:
    key: EquipmentKey
    label_ja: str
    planned_fan_count: int
    power_kw_per_fan: Decimal
    power_source_kind: Literal["industry_guidance", "manufacturer_spec"]
    count_source_kind: Literal["user_input", "demo_assumption"]
    coverage_status: EquipmentCoverageStatus
    covered_cow_count: int | None
    annual_electricity_yen: Decimal
    incremental_capex_yen: Decimal | None
    break_even_milk_kg_per_cow_day: Decimal | None
    next_confirmation_ja: str


def _electricity_only(
    fan_count: int,
    power_kw_per_fan: Decimal,
    assumptions: FinancialAssumptions,
) -> Decimal:
    result = calculate_financial_screening(
        FinancialPlan(
            additional_fan_count=fan_count,
            newly_covered_cow_count=0,
        ),
        replace(
            assumptions,
            installed_cost_yen_per_fan=Decimal("0"),
            power_kw_per_fan=power_kw_per_fan,
            avoided_milk_loss_kg_per_cow_day=None,
        ),
    )
    return result.incremental_annual_electricity_cost_yen


def build_equipment_branches(
    *,
    standard_fan_count: int,
    standard_covered_cow_count: int,
    assumptions: FinancialAssumptions,
    standard_coverage_confirmed: bool = False,
) -> tuple[EquipmentBranch, EquipmentBranch, EquipmentBranch]:
    """Return one complete standard branch and two intentionally partial ones."""

    standard_result = calculate_financial_screening(
        FinancialPlan(
            additional_fan_count=standard_fan_count,
            newly_covered_cow_count=standard_covered_cow_count,
        ),
        assumptions,
    )
    standard_status: EquipmentCoverageStatus
    if standard_fan_count == 0:
        standard_status = "not_applicable"
    elif standard_coverage_confirmed:
        standard_status = "confirmed_measurement"
    else:
        standard_status = "guidance_estimate"

    standard = EquipmentBranch(
        key="standard_100",
        label_ja="標準100cm級",
        planned_fan_count=standard_fan_count,
        power_kw_per_fan=assumptions.power_kw_per_fan,
        power_source_kind="industry_guidance",
        count_source_kind="user_input",
        coverage_status=standard_status,
        covered_cow_count=standard_covered_cow_count,
        annual_electricity_yen=(
            standard_result.incremental_annual_electricity_cost_yen
        ),
        incremental_capex_yen=standard_result.incremental_capex_yen,
        break_even_milk_kg_per_cow_day=(
            standard_result.break_even_milk_kg_per_cow_day
        ),
        next_confirmation_ja="設置候補範囲の牛体付近風速を確認",
    )
    efficient = EquipmentBranch(
        key="efficient_100",
        label_ja="省電力100cm級",
        planned_fan_count=standard_fan_count,
        power_kw_per_fan=Decimal("0.25"),
        power_source_kind="manufacturer_spec",
        count_source_kind="demo_assumption",
        coverage_status="needs_measurement",
        covered_cow_count=None,
        annual_electricity_yen=_electricity_only(
            standard_fan_count, Decimal("0.25"), assumptions
        ),
        incremental_capex_yen=None,
        break_even_milk_kg_per_cow_day=None,
        next_confirmation_ja="必要台数とカバー範囲を現地で確認",
    )
    large_count = 2 if standard_fan_count > 0 else 0
    large = EquipmentBranch(
        key="large_high_airflow",
        label_ja="大型高風量型",
        planned_fan_count=large_count,
        power_kw_per_fan=Decimal("1.055"),
        power_source_kind="manufacturer_spec",
        count_source_kind="demo_assumption",
        coverage_status="needs_measurement",
        covered_cow_count=None,
        annual_electricity_yen=_electricity_only(
            large_count, Decimal("1.055"), assumptions
        ),
        incremental_capex_yen=None,
        break_even_milk_kg_per_cow_day=None,
        next_confirmation_ja="必要台数とカバー範囲を現地で確認",
    )
    return standard, efficient, large

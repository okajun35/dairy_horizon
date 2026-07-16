"""Annual project economics for one heat-countermeasure plan."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.annual_heat_benefit import (
    AnnualHeatBenefitInput,
    calculate_annual_heat_benefit,
)
from app.financial_screening import (
    FinancialAssumptions,
    FinancialPlan,
    calculate_financial_screening,
)


ProjectAnnualEconomicsStatus = Literal[
    "not_applicable",
    "effect_unconfirmed",
    "calculable",
]


@dataclass(frozen=True)
class ProjectAnnualEconomicsResult:
    status: ProjectAnnualEconomicsStatus
    annual_avoided_milk_kg: Decimal | None
    annual_gross_milk_value_yen: Decimal | None
    annual_contribution_benefit_yen: Decimal | None
    annual_electricity_cost_yen: Decimal
    annualized_capex_yen: Decimal
    annual_project_burden_yen: Decimal
    annual_project_balance_yen: Decimal | None


def calculate_project_annual_economics(
    plan: FinancialPlan,
    assumptions: FinancialAssumptions,
) -> ProjectAnnualEconomicsResult:
    """Combine annual heat benefit with annualized incremental project costs."""

    financial = calculate_financial_screening(plan, assumptions)
    if plan.additional_fan_count == 0:
        return ProjectAnnualEconomicsResult(
            status="not_applicable",
            annual_avoided_milk_kg=None,
            annual_gross_milk_value_yen=None,
            annual_contribution_benefit_yen=None,
            annual_electricity_cost_yen=financial.incremental_annual_electricity_cost_yen,
            annualized_capex_yen=financial.annualized_capex_yen,
            annual_project_burden_yen=financial.annual_burden_yen,
            annual_project_balance_yen=None,
        )

    avoided_milk = assumptions.avoided_milk_loss_kg_per_cow_day
    if avoided_milk is None:
        return ProjectAnnualEconomicsResult(
            status="effect_unconfirmed",
            annual_avoided_milk_kg=None,
            annual_gross_milk_value_yen=None,
            annual_contribution_benefit_yen=None,
            annual_electricity_cost_yen=financial.incremental_annual_electricity_cost_yen,
            annualized_capex_yen=financial.annualized_capex_yen,
            annual_project_burden_yen=financial.annual_burden_yen,
            annual_project_balance_yen=None,
        )

    benefit = calculate_annual_heat_benefit(
        AnnualHeatBenefitInput(
            newly_covered_cow_count=plan.newly_covered_cow_count,
            heat_days_per_year=assumptions.heat_days_per_year,
            avoided_milk_loss_kg_per_cow_day=avoided_milk,
            milk_price_yen_per_kg=assumptions.milk_price_yen_per_kg,
            variable_cost_ratio=assumptions.variable_cost_ratio,
        )
    )
    return ProjectAnnualEconomicsResult(
        status="calculable",
        annual_avoided_milk_kg=benefit.annual_avoided_milk_kg,
        annual_gross_milk_value_yen=benefit.annual_gross_milk_value_yen,
        annual_contribution_benefit_yen=benefit.annual_contribution_benefit_yen,
        annual_electricity_cost_yen=financial.incremental_annual_electricity_cost_yen,
        annualized_capex_yen=financial.annualized_capex_yen,
        annual_project_burden_yen=financial.annual_burden_yen,
        annual_project_balance_yen=(
            benefit.annual_contribution_benefit_yen - financial.annual_burden_yen
        ),
    )

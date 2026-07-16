"""Compare annual heat-loss exposure before and after one fan plan."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.annual_heat_benefit import (
    AnnualHeatBenefitInput,
    AnnualHeatBenefitInputError,
    calculate_annual_heat_benefit,
)


ZERO = Decimal("0")


class AnnualHeatPathInputError(ValueError):
    """Raised when an annual heat-path input is outside its boundary."""


@dataclass(frozen=True)
class AnnualHeatPathInput:
    initial_uncovered_cow_count: int
    newly_covered_cow_count: int
    heat_days_per_year: Decimal
    milk_loss_kg_per_cow_day: Decimal
    milk_price_yen_per_kg: Decimal
    variable_cost_ratio: Decimal
    annual_project_burden_yen: Decimal


@dataclass(frozen=True)
class AnnualHeatPathResult:
    remaining_uncovered_cow_count: int
    no_action_milk_loss_kg: Decimal
    no_action_gross_milk_loss_yen: Decimal
    no_action_contribution_loss_yen: Decimal
    remaining_milk_loss_kg: Decimal
    remaining_gross_milk_loss_yen: Decimal
    remaining_contribution_loss_yen: Decimal
    annual_project_burden_yen: Decimal
    annual_total_adverse_impact_yen: Decimal
    improvement_vs_no_action_yen: Decimal


def _loss_for_cows(
    inputs: AnnualHeatPathInput,
    cow_count: int,
):
    return calculate_annual_heat_benefit(
        AnnualHeatBenefitInput(
            newly_covered_cow_count=cow_count,
            heat_days_per_year=inputs.heat_days_per_year,
            avoided_milk_loss_kg_per_cow_day=inputs.milk_loss_kg_per_cow_day,
            milk_price_yen_per_kg=inputs.milk_price_yen_per_kg,
            variable_cost_ratio=inputs.variable_cost_ratio,
        )
    )


def calculate_annual_heat_path(
    inputs: AnnualHeatPathInput,
) -> AnnualHeatPathResult:
    """Compare remaining loss and added burden with a no-action baseline.

    The result is a heat-countermeasure comparison, not whole-farm profit.
    Coverage and milk loss must already be supported by user input or a
    separately labelled assumption.
    """

    if inputs.initial_uncovered_cow_count < 0:
        raise AnnualHeatPathInputError(
            "対策前の未カバー頭数は0頭以上で入力してください。"
        )
    if not 0 <= inputs.newly_covered_cow_count <= inputs.initial_uncovered_cow_count:
        raise AnnualHeatPathInputError(
            "新規カバー頭数は対策前の未カバー頭数以下で入力してください。"
        )
    if (
        not inputs.annual_project_burden_yen.is_finite()
        or inputs.annual_project_burden_yen < ZERO
    ):
        raise AnnualHeatPathInputError(
            "設備の年間負担は0円以上の有限値で入力してください。"
        )

    try:
        no_action = _loss_for_cows(inputs, inputs.initial_uncovered_cow_count)
        remaining_count = (
            inputs.initial_uncovered_cow_count - inputs.newly_covered_cow_count
        )
        remaining = _loss_for_cows(inputs, remaining_count)
    except AnnualHeatBenefitInputError as exc:
        raise AnnualHeatPathInputError(str(exc)) from exc

    total_adverse = (
        remaining.annual_contribution_benefit_yen
        + inputs.annual_project_burden_yen
    )
    return AnnualHeatPathResult(
        remaining_uncovered_cow_count=remaining_count,
        no_action_milk_loss_kg=no_action.annual_avoided_milk_kg,
        no_action_gross_milk_loss_yen=no_action.annual_gross_milk_value_yen,
        no_action_contribution_loss_yen=(
            no_action.annual_contribution_benefit_yen
        ),
        remaining_milk_loss_kg=remaining.annual_avoided_milk_kg,
        remaining_gross_milk_loss_yen=remaining.annual_gross_milk_value_yen,
        remaining_contribution_loss_yen=(
            remaining.annual_contribution_benefit_yen
        ),
        annual_project_burden_yen=inputs.annual_project_burden_yen,
        annual_total_adverse_impact_yen=total_adverse,
        improvement_vs_no_action_yen=(
            no_action.annual_contribution_benefit_yen - total_adverse
        ),
    )

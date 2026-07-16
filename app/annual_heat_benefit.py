"""Deterministic bridge from heat-countermeasure evidence to annual benefit."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


ZERO = Decimal("0")
ONE = Decimal("1")
MAX_DAYS_PER_YEAR = Decimal("366")


class AnnualHeatBenefitInputError(ValueError):
    """Raised when an annual heat-benefit input is outside its unit boundary."""


@dataclass(frozen=True)
class AnnualHeatBenefitInput:
    newly_covered_cow_count: int
    heat_days_per_year: Decimal
    avoided_milk_loss_kg_per_cow_day: Decimal
    milk_price_yen_per_kg: Decimal
    variable_cost_ratio: Decimal


@dataclass(frozen=True)
class AnnualHeatBenefitResult:
    annual_avoided_milk_kg: Decimal
    annual_gross_milk_value_yen: Decimal
    annual_contribution_benefit_yen: Decimal


def _validate(inputs: AnnualHeatBenefitInput) -> None:
    decimal_values = (
        inputs.heat_days_per_year,
        inputs.avoided_milk_loss_kg_per_cow_day,
        inputs.milk_price_yen_per_kg,
        inputs.variable_cost_ratio,
    )
    if any(not value.is_finite() for value in decimal_values):
        raise AnnualHeatBenefitInputError("年間便益の入力は有限値で指定してください。")
    if inputs.newly_covered_cow_count < 0:
        raise AnnualHeatBenefitInputError("新規カバー頭数は0頭以上で入力してください。")
    if not ZERO <= inputs.heat_days_per_year <= MAX_DAYS_PER_YEAR:
        raise AnnualHeatBenefitInputError("THI対象日数は0〜366日で入力してください。")
    if inputs.avoided_milk_loss_kg_per_cow_day < ZERO:
        raise AnnualHeatBenefitInputError(
            "防止乳量差は0kg/頭・日以上で入力してください。"
        )
    if inputs.milk_price_yen_per_kg < ZERO:
        raise AnnualHeatBenefitInputError("実現乳価は0円/kg以上で入力してください。")
    if not ZERO <= inputs.variable_cost_ratio < ONE:
        raise AnnualHeatBenefitInputError("変動費率は0以上1未満で入力してください。")


def calculate_annual_heat_benefit(
    inputs: AnnualHeatBenefitInput,
) -> AnnualHeatBenefitResult:
    """Calculate annual avoided milk and its contribution value.

    The function does not infer airflow coverage or milk response. Both must be
    supplied as either explicit user evidence or a separately labelled
    assumption.
    """

    _validate(inputs)
    annual_avoided_milk = (
        Decimal(inputs.newly_covered_cow_count)
        * inputs.heat_days_per_year
        * inputs.avoided_milk_loss_kg_per_cow_day
    )
    gross_value = annual_avoided_milk * inputs.milk_price_yen_per_kg
    contribution_benefit = gross_value * (ONE - inputs.variable_cost_ratio)
    return AnnualHeatBenefitResult(
        annual_avoided_milk_kg=annual_avoided_milk,
        annual_gross_milk_value_yen=gross_value,
        annual_contribution_benefit_yen=contribution_benefit,
    )

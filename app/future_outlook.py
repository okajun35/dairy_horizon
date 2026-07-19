"""Deterministic, condition-by-condition sensitivity view for phase one."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

from app.financial_screening import FinancialAssumptions, FinancialPlan
from app.project_annual_economics import calculate_project_annual_economics


ZERO = Decimal("0")
ONE_AND_A_HALF = Decimal("1.5")
SensitivityStatus = Literal["reachable", "always_negative", "always_positive"]


@dataclass(frozen=True)
class FutureOutlookPoint:
    value: Decimal
    annual_project_balance_yen: Decimal
    is_break_even: bool


@dataclass(frozen=True)
class FutureOutlookControl:
    key: Literal[
        "avoided_milk_loss_kg_per_cow_day",
        "milk_price_yen_per_kg",
        "electricity_price_yen_per_kwh",
        "operating_hours_per_day",
    ]
    label_ja: str
    unit_ja: str
    step: Decimal
    status: SensitivityStatus
    break_even_value: Decimal | None
    points: tuple[FutureOutlookPoint, ...]


@dataclass(frozen=True)
class FutureOutlook:
    first_phase_additional_fan_count: int
    second_phase_candidate_fan_count: int
    controls: tuple[FutureOutlookControl, ...]


_CONTROL_SPECS = (
    (
        "avoided_milk_loss_kg_per_cow_day",
        "暑い日に防げた乳量低下",
        "kg／頭・暑熱日",
        Decimal("0.1"),
        None,
    ),
    (
        "milk_price_yen_per_kg",
        "実現乳価",
        "円／kg",
        Decimal("1"),
        None,
    ),
    (
        "electricity_price_yen_per_kwh",
        "電力量単価",
        "円／kWh",
        Decimal("1"),
        None,
    ),
    (
        "operating_hours_per_day",
        "暑い日の運転時間",
        "時間／日",
        Decimal("0.1"),
        Decimal("24"),
    ),
)


def _balance(
    plan: FinancialPlan,
    assumptions: FinancialAssumptions,
    key: str,
    value: Decimal,
) -> Decimal:
    economics = calculate_project_annual_economics(
        plan, replace(assumptions, **{key: value})
    )
    assert economics.annual_project_balance_yen is not None
    return economics.annual_project_balance_yen


def _find_break_even(
    plan: FinancialPlan,
    assumptions: FinancialAssumptions,
    key: str,
    lower: Decimal,
    upper: Decimal,
) -> tuple[SensitivityStatus, Decimal | None]:
    """Find a zero crossing without copying the annual economics formula."""

    lower_balance = _balance(plan, assumptions, key, lower)
    upper_balance = _balance(plan, assumptions, key, upper)
    if lower_balance == ZERO:
        return "reachable", lower
    if upper_balance == ZERO:
        return "reachable", upper
    if lower_balance * upper_balance > ZERO:
        return (
            ("always_negative" if lower_balance < ZERO else "always_positive"),
            None,
        )

    low = lower
    high = upper
    for _ in range(80):
        middle = (low + high) / Decimal("2")
        middle_balance = _balance(plan, assumptions, key, middle)
        if middle_balance == ZERO:
            return "reachable", middle
        if lower_balance * middle_balance < ZERO:
            high = middle
        else:
            low = middle
            lower_balance = middle_balance
    return "reachable", (low + high) / Decimal("2")


def _anchored_values(
    *, lower: Decimal, upper: Decimal, anchor: Decimal, step: Decimal
) -> tuple[Decimal, ...]:
    """Keep the exact zero-balance point while offering fixed-size movements."""

    values = {lower, anchor, upper}
    value = anchor - step
    while value > lower:
        values.add(value)
        value -= step
    value = anchor + step
    while value < upper:
        values.add(value)
        value += step
    return tuple(sorted(values))


def _control(
    *,
    plan: FinancialPlan,
    assumptions: FinancialAssumptions,
    key: Literal[
        "avoided_milk_loss_kg_per_cow_day",
        "milk_price_yen_per_kg",
        "electricity_price_yen_per_kwh",
        "operating_hours_per_day",
    ],
    label_ja: str,
    unit_ja: str,
    step: Decimal,
    fixed_upper: Decimal | None,
) -> FutureOutlookControl:
    baseline_value = getattr(assumptions, key)
    assert baseline_value is not None
    lower = ZERO
    probe_upper = fixed_upper or max(baseline_value, ONE_AND_A_HALF) * Decimal("100")
    status, break_even = _find_break_even(
        plan, assumptions, key, lower, probe_upper
    )
    if status != "reachable" or break_even is None:
        return FutureOutlookControl(
            key=key,
            label_ja=label_ja,
            unit_ja=unit_ja,
            step=step,
            status=status,
            break_even_value=None,
            points=(
                FutureOutlookPoint(
                    value=lower,
                    annual_project_balance_yen=_balance(plan, assumptions, key, lower),
                    is_break_even=False,
                ),
                FutureOutlookPoint(
                    value=probe_upper,
                    annual_project_balance_yen=_balance(
                        plan, assumptions, key, probe_upper
                    ),
                    is_break_even=False,
                ),
            ),
        )
    upper = fixed_upper or break_even * ONE_AND_A_HALF
    values = _anchored_values(lower=lower, upper=upper, anchor=break_even, step=step)
    return FutureOutlookControl(
        key=key,
        label_ja=label_ja,
        unit_ja=unit_ja,
        step=step,
        status="reachable",
        break_even_value=break_even,
        points=tuple(
            FutureOutlookPoint(
                value=value,
                annual_project_balance_yen=(
                    ZERO if value == break_even else _balance(plan, assumptions, key, value)
                ),
                is_break_even=value == break_even,
            )
            for value in values
        ),
    )


def build_future_outlook(
    *,
    first_phase_plan: FinancialPlan,
    full_additional_fan_count: int,
    assumptions: FinancialAssumptions,
) -> FutureOutlook:
    """Build four independent, deterministic sensitivity controls.

    Each control changes one condition and holds the other effective
    assumptions fixed.  This is a sensitivity display, never a forecast.
    """

    controls = tuple(
        _control(
            plan=first_phase_plan,
            assumptions=assumptions,
            key=key,
            label_ja=label_ja,
            unit_ja=unit_ja,
            step=step,
            fixed_upper=fixed_upper,
        )
        for key, label_ja, unit_ja, step, fixed_upper in _CONTROL_SPECS
    )
    return FutureOutlook(
        first_phase_additional_fan_count=first_phase_plan.additional_fan_count,
        second_phase_candidate_fan_count=max(
            0, full_additional_fan_count - first_phase_plan.additional_fan_count
        ),
        controls=controls,
    )

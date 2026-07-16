"""Deterministic current/future screening for one staged fan investment.

The module intentionally compares two snapshots. It does not interpolate herd
size, calculate cumulative ROI, recommend an investment year, or infer airflow
coverage from climate data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.navigator import COWS_PER_FAN, guideline_fan_count


HerdDirection = Literal["decrease", "maintain", "increase"]
CoverageStatus = Literal[
    "not_applicable",
    "guidance_estimate",
    "confirmed_measurement",
]
NextCheckKey = Literal[
    "future_target_cow_count",
    "cow_level_wind_speed",
    "summer_milk_difference",
]


class AdaptationInputError(ValueError):
    """Raised when a two-horizon screening input is outside its boundary."""


@dataclass(frozen=True)
class TwoHorizonInput:
    current_target_cow_count: int
    future_target_cow_count: int | None
    existing_fan_count: int
    first_phase_additional_fan_count: int
    horizon_years: int
    confirmed_covered_cow_count: int | None = None


@dataclass(frozen=True)
class HorizonCapacityState:
    target_cow_count: int
    active_fan_count: int
    guideline_fan_count: int
    guideline_gap_fan_count: int
    estimated_uncovered_cow_count: int


@dataclass(frozen=True)
class TwoHorizonScreening:
    inputs: TwoHorizonInput
    current_before: HorizonCapacityState
    current_after: HorizonCapacityState
    future_after: HorizonCapacityState | None
    herd_direction: HerdDirection | None
    transition_has_guideline_gap: bool
    assumed_newly_covered_cow_count: int
    covered_cow_count_for_finance: int
    coverage_status: CoverageStatus
    next_check_key: NextCheckKey


def _validate(inputs: TwoHorizonInput) -> None:
    if not 1 <= inputs.current_target_cow_count <= 300:
        raise AdaptationInputError("現在の対策対象頭数は1〜300頭で入力してください。")
    if inputs.future_target_cow_count is not None and not (
        1 <= inputs.future_target_cow_count <= 300
    ):
        raise AdaptationInputError("将来の対策対象頭数は1〜300頭で入力してください。")
    if inputs.existing_fan_count < 0:
        raise AdaptationInputError("既存ファン数は0台以上で入力してください。")
    if inputs.first_phase_additional_fan_count < 0:
        raise AdaptationInputError("第1期の追加台数は0台以上で入力してください。")
    if not 1 <= inputs.horizon_years <= 20:
        raise AdaptationInputError("将来までの期間は1〜20年で入力してください。")
    if (
        inputs.confirmed_covered_cow_count is not None
        and inputs.confirmed_covered_cow_count < 0
    ):
        raise AdaptationInputError("確認できたカバー頭数は0頭以上で入力してください。")


def _capacity_state(target_cows: int, active_fans: int) -> HorizonCapacityState:
    guideline = guideline_fan_count(target_cows)
    return HorizonCapacityState(
        target_cow_count=target_cows,
        active_fan_count=active_fans,
        guideline_fan_count=guideline,
        guideline_gap_fan_count=max(0, guideline - active_fans),
        estimated_uncovered_cow_count=max(
            0, target_cows - active_fans * COWS_PER_FAN
        ),
    )


def _direction(current_cows: int, future_cows: int) -> HerdDirection:
    if future_cows < current_cows:
        return "decrease"
    if future_cows > current_cows:
        return "increase"
    return "maintain"


def build_two_horizon_screening(
    inputs: TwoHorizonInput,
) -> TwoHorizonScreening:
    """Compare one first-phase investment at the current and future herd size."""

    _validate(inputs)
    current_before = _capacity_state(
        inputs.current_target_cow_count, inputs.existing_fan_count
    )
    active_after = (
        inputs.existing_fan_count + inputs.first_phase_additional_fan_count
    )
    current_after = _capacity_state(inputs.current_target_cow_count, active_after)
    future_after = (
        _capacity_state(inputs.future_target_cow_count, active_after)
        if inputs.future_target_cow_count is not None
        else None
    )

    assumed_newly_covered = min(
        inputs.first_phase_additional_fan_count * COWS_PER_FAN,
        current_before.estimated_uncovered_cow_count,
    )
    if (
        inputs.confirmed_covered_cow_count is not None
        and inputs.confirmed_covered_cow_count > assumed_newly_covered
    ):
        raise AdaptationInputError(
            "確認できたカバー頭数は、頭数基準による新規カバー想定頭数以下で入力してください。"
        )

    if inputs.first_phase_additional_fan_count == 0:
        coverage_status: CoverageStatus = "not_applicable"
        covered_for_finance = 0
    elif inputs.confirmed_covered_cow_count is None:
        coverage_status = "guidance_estimate"
        covered_for_finance = assumed_newly_covered
    else:
        coverage_status = "confirmed_measurement"
        covered_for_finance = inputs.confirmed_covered_cow_count

    if inputs.future_target_cow_count is None:
        next_check: NextCheckKey = "future_target_cow_count"
    elif coverage_status != "confirmed_measurement":
        next_check = "cow_level_wind_speed"
    else:
        next_check = "summer_milk_difference"

    return TwoHorizonScreening(
        inputs=inputs,
        current_before=current_before,
        current_after=current_after,
        future_after=future_after,
        herd_direction=(
            _direction(
                inputs.current_target_cow_count, inputs.future_target_cow_count
            )
            if inputs.future_target_cow_count is not None
            else None
        ),
        transition_has_guideline_gap=current_after.guideline_gap_fan_count > 0,
        assumed_newly_covered_cow_count=assumed_newly_covered,
        covered_cow_count_for_finance=covered_for_finance,
        coverage_status=coverage_status,
        next_check_key=next_check,
    )

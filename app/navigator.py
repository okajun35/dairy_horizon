"""Deterministic barn-first adaptation pathway calculations.

The navigator deliberately answers only the first questions: what is missing
today, what a small first step covers, and what to confirm next.  It does not
select an investment year or make a climate forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal


COWS_PER_FAN = 3
DEFAULT_FIRST_PHASE_FAN_COUNT = 5


@dataclass(frozen=True)
class BarnInput:
    lactating_cows: int
    lane_count: int
    existing_fan_count: int
    first_phase_fan_count: int | None = None
    region_ja: str = "千葉市"


@dataclass(frozen=True)
class FanPlan:
    key: Literal["current", "first_phase", "full_coverage"]
    label_ja: str
    additional_fan_count: int
    active_fan_count: int
    covered_cow_ids: tuple[str, ...]
    newly_covered_cow_ids: tuple[str, ...]
    status: Literal["NOT_REQUIRED", "READY_TO_CONFIRM"]


@dataclass(frozen=True)
class BarnNavigation:
    inputs: BarnInput
    cows_by_lane: tuple[tuple[str, ...], ...]
    required_fans_by_lane: tuple[int, ...]
    required_fan_count: int
    shortage_fan_count: int
    plans: tuple[FanPlan, ...]
    next_question_ja: str
    next_action_ja: str


class InputValidationError(ValueError):
    """Raised when a small-input barn request cannot be evaluated."""


def _validate(inputs: BarnInput) -> None:
    if not 1 <= inputs.lactating_cows <= 300:
        raise InputValidationError("搾乳牛頭数は1〜300頭で入力してください。")
    if inputs.lane_count not in {1, 2}:
        raise InputValidationError("牛床列数は1列または2列で入力してください。")
    if inputs.existing_fan_count < 0:
        raise InputValidationError("既存ファン数は0以上で入力してください。")


def distribute_cows_by_lane(lactating_cows: int, lane_count: int) -> tuple[tuple[str, ...], ...]:
    """Split cows deterministically; 75 cows in two lanes becomes 38 and 37."""
    base, remainder = divmod(lactating_cows, lane_count)
    next_cow = 1
    lanes: list[tuple[str, ...]] = []
    for lane_index in range(lane_count):
        count = base + (1 if lane_index < remainder else 0)
        lanes.append(tuple(f"C{cow:03d}" for cow in range(next_cow, next_cow + count)))
        next_cow += count
    return tuple(lanes)


def required_fans_by_lane(cows_by_lane: tuple[tuple[str, ...], ...]) -> tuple[int, ...]:
    return tuple(ceil(len(cows) / COWS_PER_FAN) for cows in cows_by_lane)


def _allocate_fans(total_fans: int, required_by_lane: tuple[int, ...]) -> tuple[int, ...]:
    """Spread installed fans across lanes before filling either lane completely."""
    allocated = [0 for _ in required_by_lane]
    remaining = max(0, total_fans)
    while remaining and any(count < required for count, required in zip(allocated, required_by_lane, strict=True)):
        for index, required in enumerate(required_by_lane):
            if remaining == 0:
                break
            if allocated[index] < required:
                allocated[index] += 1
                remaining -= 1
    return tuple(allocated)


def _covered_cows(cows_by_lane: tuple[tuple[str, ...], ...], fans_by_lane: tuple[int, ...]) -> tuple[str, ...]:
    covered: list[str] = []
    for cows, fan_count in zip(cows_by_lane, fans_by_lane, strict=True):
        covered.extend(cows[: fan_count * COWS_PER_FAN])
    return tuple(covered)


def _plan(
    key: Literal["current", "first_phase", "full_coverage"],
    label_ja: str,
    additional_fans: int,
    inputs: BarnInput,
    cows_by_lane: tuple[tuple[str, ...], ...],
    required_by_lane: tuple[int, ...],
    baseline_covered: tuple[str, ...],
    shortage: int,
) -> FanPlan:
    active_fans = min(sum(required_by_lane), inputs.existing_fan_count + additional_fans)
    covered = _covered_cows(cows_by_lane, _allocate_fans(active_fans, required_by_lane))
    baseline = set(baseline_covered)
    status = "NOT_REQUIRED" if shortage == 0 else "READY_TO_CONFIRM"
    return FanPlan(
        key=key,
        label_ja=label_ja,
        additional_fan_count=additional_fans,
        active_fan_count=active_fans,
        covered_cow_ids=covered,
        newly_covered_cow_ids=tuple(cow_id for cow_id in covered if cow_id not in baseline),
        status=status,
    )


def build_navigation(inputs: BarnInput) -> BarnNavigation:
    _validate(inputs)
    cows_by_lane = distribute_cows_by_lane(inputs.lactating_cows, inputs.lane_count)
    required_by_lane = required_fans_by_lane(cows_by_lane)
    required_count = sum(required_by_lane)
    shortage = max(0, required_count - inputs.existing_fan_count)
    baseline_covered = _covered_cows(
        cows_by_lane,
        _allocate_fans(inputs.existing_fan_count, required_by_lane),
    )
    if inputs.first_phase_fan_count is None:
        first_phase = min(DEFAULT_FIRST_PHASE_FAN_COUNT, shortage)
    else:
        if not 0 <= inputs.first_phase_fan_count <= shortage:
            raise InputValidationError(f"第1期に追加する台数は、不足{shortage}台の範囲で入力してください。")
        first_phase = inputs.first_phase_fan_count
    plans = (
        _plan("current", "現在", 0, inputs, cows_by_lane, required_by_lane, baseline_covered, shortage),
        _plan("first_phase", "第1期：小さく始める", first_phase, inputs, cows_by_lane, required_by_lane, baseline_covered, shortage),
        _plan("full_coverage", "全数整備", shortage, inputs, cows_by_lane, required_by_lane, baseline_covered, shortage),
    )
    if shortage == 0:
        question = "暑い日に、実際に風が届いていない牛床はどこですか？"
        action = "既存ファンの位置と稼働状況を牛床ごとに確認します。"
    else:
        question = "暑い日に、未カバーの牛床で牛がどのように過ごしていますか？"
        action = "未カバー推計の牛床を見ながら、風が届く範囲と牛の様子を確認します。"
    return BarnNavigation(
        inputs=inputs,
        cows_by_lane=cows_by_lane,
        required_fans_by_lane=required_by_lane,
        required_fan_count=required_count,
        shortage_fan_count=shortage,
        plans=plans,
        next_question_ja=question,
        next_action_ja=action,
    )

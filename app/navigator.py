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
FAN_COVERAGE_SOURCE_ID = "zenrakuren_cowbell_178"
FanCountBasis = Literal[
    "zenrakuren_headcount_guideline",
    "user_input",
    "contractor_plan",
    "layout_estimate",
]


@dataclass(frozen=True)
class BarnInput:
    lactating_cows: int
    lane_count: int
    existing_fan_count: int
    first_phase_fan_count: int | None = None
    region_ja: str = "千葉市"
    planned_fan_count: int | None = None


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
class CurrentBarnState:
    """Current headcount-guideline gap with evidence boundaries attached."""

    guideline_fans_by_lane_for_display: tuple[int, ...]
    guideline_fan_count: int
    guideline_fan_count_basis: Literal["zenrakuren_headcount_guideline"]
    existing_fan_count: int
    guideline_gap_fan_count: int
    assumed_existing_fans_by_lane: tuple[int, ...]
    estimated_covered_cow_ids: tuple[str, ...]
    estimated_uncovered_cow_ids: tuple[str, ...]
    fan_capacity_cows_per_unit: int
    coverage_basis_kind: Literal["industry_guidance"]
    coverage_source_id: Literal["zenrakuren_cowbell_178"]
    placement_basis_kind: Literal["demo_assumption"]
    placement_note_ja: str
    needs_field_confirmation: bool


@dataclass(frozen=True)
class BarnNavigation:
    inputs: BarnInput
    current_state: CurrentBarnState
    cows_by_lane: tuple[tuple[str, ...], ...]
    guideline_fans_by_lane_for_display: tuple[int, ...]
    guideline_fan_count: int
    guideline_gap_fan_count: int
    planned_fan_count: int | None
    evaluation_fan_count: int
    evaluation_additional_fan_count: int
    fan_count_basis: FanCountBasis
    plans: tuple[FanPlan, ...]
    next_question_ja: str
    next_action_ja: str


class InputValidationError(ValueError):
    """Raised when a small-input barn request cannot be evaluated."""


def _validate(inputs: BarnInput) -> None:
    if not 1 <= inputs.lactating_cows <= 300:
        raise InputValidationError("搾乳牛頭数は1〜300頭で入力してください。")
    if not 1 <= inputs.lane_count <= 6:
        raise InputValidationError("牛床列数は1〜6列で入力してください。")
    if inputs.existing_fan_count < 0:
        raise InputValidationError("既存ファン数は0以上で入力してください。")
    if inputs.planned_fan_count is not None and inputs.planned_fan_count < inputs.existing_fan_count:
        raise InputValidationError("今回の計画総台数は、既存ファン数以上で入力してください。")


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


def guideline_fan_count(lactating_cows: int, cows_per_fan: int = COWS_PER_FAN) -> int:
    """Return the headcount-only Zenrakuren planning guideline."""
    return ceil(lactating_cows / cows_per_fan)


def _distribute_count(total: int, lane_count: int) -> tuple[int, ...]:
    base, remainder = divmod(total, lane_count)
    return tuple(base + (1 if index < remainder else 0) for index in range(lane_count))


def guideline_fans_by_lane_for_display(cows_by_lane: tuple[tuple[str, ...], ...]) -> tuple[int, ...]:
    """Distribute the headcount guideline for display; not a layout design."""
    total_cows = sum(len(cows) for cows in cows_by_lane)
    return _distribute_count(guideline_fan_count(total_cows), len(cows_by_lane))


def _estimated_covered_cows(cows_by_lane: tuple[tuple[str, ...], ...], active_fans: int) -> tuple[str, ...]:
    """Spread headcount capacity across lanes for display without claiming airflow geometry."""
    coverage_slots = min(sum(len(cows) for cows in cows_by_lane), active_fans * COWS_PER_FAN)
    covered_by_lane = [0 for _ in cows_by_lane]
    remaining = coverage_slots
    while remaining:
        for index, cows in enumerate(cows_by_lane):
            if remaining == 0:
                break
            if covered_by_lane[index] < len(cows):
                covered_by_lane[index] += 1
                remaining -= 1
    return tuple(
        cow_id
        for cows, covered_count in zip(cows_by_lane, covered_by_lane, strict=True)
        for cow_id in cows[:covered_count]
    )


def _plan(
    key: Literal["current", "first_phase", "full_coverage"],
    label_ja: str,
    additional_fans: int,
    inputs: BarnInput,
    cows_by_lane: tuple[tuple[str, ...], ...],
    baseline_covered: tuple[str, ...],
    investment_required: bool,
) -> FanPlan:
    active_fans = inputs.existing_fan_count + additional_fans
    covered = _estimated_covered_cows(cows_by_lane, active_fans)
    baseline = set(baseline_covered)
    status = "READY_TO_CONFIRM" if investment_required else "NOT_REQUIRED"
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
    guideline_by_lane = guideline_fans_by_lane_for_display(cows_by_lane)
    guideline_count = guideline_fan_count(inputs.lactating_cows)
    guideline_gap = max(0, guideline_count - inputs.existing_fan_count)
    evaluation_count = inputs.planned_fan_count if inputs.planned_fan_count is not None else guideline_count
    evaluation_additional = max(0, evaluation_count - inputs.existing_fan_count)
    fan_count_basis: FanCountBasis = (
        "user_input" if inputs.planned_fan_count is not None else "zenrakuren_headcount_guideline"
    )
    assumed_existing_by_lane = _distribute_count(inputs.existing_fan_count, inputs.lane_count)
    baseline_covered = _estimated_covered_cows(cows_by_lane, inputs.existing_fan_count)
    baseline_covered_set = set(baseline_covered)
    baseline_uncovered = tuple(
        cow_id
        for lane in cows_by_lane
        for cow_id in lane
        if cow_id not in baseline_covered_set
    )
    current_state = CurrentBarnState(
        guideline_fans_by_lane_for_display=guideline_by_lane,
        guideline_fan_count=guideline_count,
        guideline_fan_count_basis="zenrakuren_headcount_guideline",
        existing_fan_count=inputs.existing_fan_count,
        guideline_gap_fan_count=guideline_gap,
        assumed_existing_fans_by_lane=assumed_existing_by_lane,
        estimated_covered_cow_ids=baseline_covered,
        estimated_uncovered_cow_ids=baseline_uncovered,
        fan_capacity_cows_per_unit=COWS_PER_FAN,
        coverage_basis_kind="industry_guidance",
        coverage_source_id=FAN_COVERAGE_SOURCE_ID,
        placement_basis_kind="demo_assumption",
        placement_note_ja="頭数基準のカバー可能頭数を牛床列へ均等に配分した画面表示用推計です。実際の送風範囲を表すものではありません。",
        needs_field_confirmation=True,
    )
    if inputs.first_phase_fan_count is None:
        first_phase = min(DEFAULT_FIRST_PHASE_FAN_COUNT, evaluation_additional)
    else:
        if not 0 <= inputs.first_phase_fan_count <= evaluation_additional:
            raise InputValidationError(
                f"第1期に追加する台数は、今回追加する{evaluation_additional}台の範囲で入力してください。"
            )
        first_phase = inputs.first_phase_fan_count
    investment_required = evaluation_additional > 0
    full_label = "今回の計画台数まで追加" if inputs.planned_fan_count is not None else "頭数目安まで追加"
    plans = (
        _plan("current", "現在", 0, inputs, cows_by_lane, baseline_covered, investment_required),
        _plan("first_phase", "第1期：小さく始める", first_phase, inputs, cows_by_lane, baseline_covered, investment_required),
        _plan("full_coverage", full_label, evaluation_additional, inputs, cows_by_lane, baseline_covered, investment_required),
    )
    if guideline_gap == 0:
        question = "暑い日に、実際に風が届いていない牛床はどこですか？"
        action = "既存ファンの位置と稼働状況を牛床ごとに確認します。"
    else:
        question = "暑い日に、未カバーの牛床で牛がどのように過ごしていますか？"
        action = "未カバー推計の牛床を見ながら、風が届く範囲と牛の様子を確認します。"
    return BarnNavigation(
        inputs=inputs,
        current_state=current_state,
        cows_by_lane=cows_by_lane,
        guideline_fans_by_lane_for_display=guideline_by_lane,
        guideline_fan_count=guideline_count,
        guideline_gap_fan_count=guideline_gap,
        planned_fan_count=inputs.planned_fan_count,
        evaluation_fan_count=evaluation_count,
        evaluation_additional_fan_count=evaluation_additional,
        fan_count_basis=fan_count_basis,
        plans=plans,
        next_question_ja=question,
        next_action_ja=action,
    )

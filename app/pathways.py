"""Deterministic year-by-year comparison of the three approved fan paths.

This module describes equipment coverage states only. It does not estimate
equipment failure, prices, climate impacts, milk loss, or an optimal year.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.navigator import BarnInput, CurrentBarnState, FanPlan, InputValidationError, build_navigation


PathKey = Literal["current", "first_phase", "full_coverage"]
MonitoringItem = Literal["cow_level_wind_speed", "uncovered_stalls", "summer_milk_difference"]
NextDecisionStatus = Literal["comparison_only", "pending_observation"]


@dataclass(frozen=True)
class PathYearState:
    year: int
    active_fan_count: int
    additional_fan_count: int
    investment_fan_count: int
    estimated_covered_cow_ids: tuple[str, ...]
    estimated_uncovered_cow_ids: tuple[str, ...]
    uncovered_cow_count: int


@dataclass(frozen=True)
class InvestmentPath:
    key: PathKey
    label_ja: str
    investment_year: int | None
    review_year: int | None
    monitoring_items: tuple[MonitoringItem, ...]
    next_decision_status: NextDecisionStatus
    years: tuple[PathYearState, ...]
    cumulative_uncovered_cow_years: int


@dataclass(frozen=True)
class PathComparison:
    current_state: CurrentBarnState
    start_year: int
    end_year: int
    planning_horizon_years: int
    paths: tuple[InvestmentPath, ...]


def _uncovered_cow_ids(all_cow_ids: tuple[str, ...], covered_cow_ids: tuple[str, ...]) -> tuple[str, ...]:
    covered = set(covered_cow_ids)
    return tuple(cow_id for cow_id in all_cow_ids if cow_id not in covered)


def _year_state(
    *,
    year: int,
    current_plan: FanPlan,
    selected_plan: FanPlan,
    investment_year: int | None,
    all_cow_ids: tuple[str, ...],
) -> PathYearState:
    investment_active = investment_year is not None and year >= investment_year
    plan = selected_plan if investment_active else current_plan
    uncovered = _uncovered_cow_ids(all_cow_ids, plan.covered_cow_ids)
    return PathYearState(
        year=year,
        active_fan_count=plan.active_fan_count,
        additional_fan_count=plan.additional_fan_count if investment_active else 0,
        investment_fan_count=plan.additional_fan_count if year == investment_year else 0,
        estimated_covered_cow_ids=plan.covered_cow_ids,
        estimated_uncovered_cow_ids=uncovered,
        uncovered_cow_count=len(uncovered),
    )


def _path(
    *,
    key: PathKey,
    label_ja: str,
    current_plan: FanPlan,
    selected_plan: FanPlan,
    years: tuple[int, ...],
    requested_investment_year: int | None,
    all_cow_ids: tuple[str, ...],
) -> InvestmentPath:
    has_investment = key != "current" and selected_plan.additional_fan_count > 0
    investment_year = requested_investment_year if has_investment else None
    yearly = tuple(
        _year_state(
            year=year,
            current_plan=current_plan,
            selected_plan=selected_plan,
            investment_year=investment_year,
            all_cow_ids=all_cow_ids,
        )
        for year in years
    )
    is_first_phase = key == "first_phase" and has_investment
    return InvestmentPath(
        key=key,
        label_ja=label_ja,
        investment_year=investment_year,
        review_year=investment_year + 1 if is_first_phase and investment_year is not None else None,
        monitoring_items=("cow_level_wind_speed", "uncovered_stalls", "summer_milk_difference") if is_first_phase else (),
        next_decision_status="pending_observation" if is_first_phase else "comparison_only",
        years=yearly,
        cumulative_uncovered_cow_years=sum(item.uncovered_cow_count for item in yearly),
    )


def build_path_comparison(
    inputs: BarnInput,
    *,
    planning_start_year: int = 2026,
    planning_horizon_years: int = 5,
    investment_year: int | None = None,
) -> PathComparison:
    """Build current, first-phase, and full-coverage annual states.

    An investment is treated as installed before that year's heat season.
    The default comparison period is five years; up to fifteen years is
    accepted for coverage-state comparisons only.
    """
    if not 1 <= planning_horizon_years <= 15:
        raise InputValidationError("比較期間は1〜15年間で入力してください。")
    years = tuple(range(planning_start_year, planning_start_year + planning_horizon_years))
    selected_investment_year = planning_start_year if investment_year is None else investment_year
    if selected_investment_year not in years:
        raise InputValidationError("投資年は比較期間内で入力してください。")

    navigation = build_navigation(inputs)
    plans = {plan.key: plan for plan in navigation.plans}
    current_plan = plans["current"]
    all_cow_ids = tuple(cow_id for lane in navigation.cows_by_lane for cow_id in lane)
    paths = tuple(
        _path(
            key=key,
            label_ja=plans[key].label_ja,
            current_plan=current_plan,
            selected_plan=plans[key],
            years=years,
            requested_investment_year=selected_investment_year,
            all_cow_ids=all_cow_ids,
        )
        for key in ("current", "first_phase", "full_coverage")
    )
    return PathComparison(
        current_state=navigation.current_state,
        start_year=years[0],
        end_year=years[-1],
        planning_horizon_years=planning_horizon_years,
        paths=paths,
    )

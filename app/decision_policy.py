"""Transparent economic reading for the three comparison cards.

This module deliberately identifies what the calculated comparison supports; it
does not choose equipment for the user.  A language model may explain this
result, but it must not replace the policy with its own recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class DeclaredPriority(StrEnum):
    """The one optional priority a user may explicitly state later."""

    AVOID_UNRECOVERED_SPENDING = "avoid_unrecovered_spending"
    AVOID_UNCOVERED_COWS = "avoid_uncovered_cows"


EconomicReading = Literal[
    "coverage_already_complete",
    "additional_options_not_economically_supported",
    "first_phase_only_economically_supported",
    "full_coverage_only_economically_supported",
    "additional_options_economically_supported",
    "full_coverage_dominates_first_phase",
]
ComparisonFocus = Literal[
    "current_only",
    "current_and_first_phase",
    "first_phase_and_full_coverage",
    "full_coverage",
]
PriorityAlignment = Literal[
    "spending_priority_declared",
    "coverage_priority_declared",
]
SelectedPosition = Literal[
    "economic_baseline",
    "economically_supported",
    "partial_coverage_beyond_economic_screen",
    "full_coverage_beyond_economic_screen",
    "coverage_already_complete",
]
AdaptivePathway = Literal["MAINTAIN", "START_SMALL", "COMPLETE_NOW", "REASSESS"]
UncoveredChange = Literal[
    "already_covered",
    "partial_reduction",
    "complete_reduction",
    "no_reduction_from_first_phase",
]
PathFlexibility = Literal["not_needed", "high", "unclear"]
EconomicGuardrail = Literal[
    "not_applicable",
    "first_phase_annual_comparison_not_negative",
    "first_phase_annual_comparison_negative",
    "full_coverage_annual_comparison_not_negative",
    "full_coverage_annual_comparison_negative",
]


@dataclass(frozen=True)
class ComparisonOption:
    """Only the deterministic comparison values relevant to the policy."""

    upfront_cost_yen: int
    remaining_uncovered_cow_count: int
    annual_comparison_yen: int


@dataclass(frozen=True)
class ThreeChoiceEvidence:
    current: ComparisonOption
    first_phase: ComparisonOption
    full_coverage: ComparisonOption


@dataclass(frozen=True)
class StandardEconomicReading:
    """A policy result, not an automatic recommendation."""

    economic_reading: EconomicReading
    comparison_focus: ComparisonFocus
    basis: tuple[str, ...]
    not_proven: tuple[str, ...]
    decision_still_belongs_to_user: bool
    declared_priority: DeclaredPriority | None
    priority_alignment: PriorityAlignment | None
    current_selected_position: SelectedPosition
    first_phase_selected_position: SelectedPosition
    full_coverage_selected_position: SelectedPosition


@dataclass(frozen=True)
class AdaptivePathwayPosition:
    """Position an improvement path without claiming a cooling outcome.

    ``uncovered`` is the deterministic placement estimate, not measured air
    speed or a guarantee of cow-level cooling.  The annual comparison remains
    a guardrail: it constrains how confidently a pathway can be presented,
    but does not become the pathway's primary objective.
    """

    overall_position: AdaptivePathway
    uncovered_change: UncoveredChange
    path_flexibility: PathFlexibility
    economic_guardrail: EconomicGuardrail
    basis: tuple[str, ...]
    not_proven: tuple[str, ...]
    decision_still_belongs_to_user: bool


def _validate_option(option: ComparisonOption) -> None:
    if option.upfront_cost_yen < 0:
        raise ValueError("先に払う額は0円以上である必要があります。")
    if option.remaining_uncovered_cow_count < 0:
        raise ValueError("未カバー推計頭数は0頭以上である必要があります。")


def _full_coverage_dominates_first_phase(evidence: ThreeChoiceEvidence) -> bool:
    first = evidence.first_phase
    full = evidence.full_coverage
    no_worse = (
        full.upfront_cost_yen <= first.upfront_cost_yen
        and full.remaining_uncovered_cow_count <= first.remaining_uncovered_cow_count
        and full.annual_comparison_yen >= first.annual_comparison_yen
    )
    strictly_better = (
        full.upfront_cost_yen < first.upfront_cost_yen
        or full.remaining_uncovered_cow_count < first.remaining_uncovered_cow_count
        or full.annual_comparison_yen > first.annual_comparison_yen
    )
    return no_worse and strictly_better


def _priority_alignment(
    declared_priority: DeclaredPriority | None,
) -> PriorityAlignment | None:
    if declared_priority is DeclaredPriority.AVOID_UNRECOVERED_SPENDING:
        return "spending_priority_declared"
    if declared_priority is DeclaredPriority.AVOID_UNCOVERED_COWS:
        return "coverage_priority_declared"
    return None


def _selected_positions(
    *,
    first_supported: bool,
    full_supported: bool,
) -> tuple[SelectedPosition, SelectedPosition, SelectedPosition]:
    """State the economic position of each explicit card selection."""

    return (
        "economic_baseline",
        (
            "economically_supported"
            if first_supported
            else "partial_coverage_beyond_economic_screen"
        ),
        (
            "economically_supported"
            if full_supported
            else "full_coverage_beyond_economic_screen"
        ),
    )


def build_standard_economic_reading(
    evidence: ThreeChoiceEvidence,
    *,
    declared_priority: DeclaredPriority | None = None,
) -> StandardEconomicReading:
    """Classify economic evidence without selecting a path for the user.

    An annual comparison of zero or greater means the given comparison is not
    negative under its stated assumptions.  It remains a screening comparison,
    never proof of investment profitability or physical cooling sufficiency.
    """

    for option in (evidence.current, evidence.first_phase, evidence.full_coverage):
        _validate_option(option)

    alignment = _priority_alignment(declared_priority)
    if evidence.current.remaining_uncovered_cow_count == 0:
        return StandardEconomicReading(
            economic_reading="coverage_already_complete",
            comparison_focus="current_only",
            basis=("current_uncovered_is_zero",),
            not_proven=("physical_cooling_sufficiency",),
            decision_still_belongs_to_user=True,
            declared_priority=declared_priority,
            priority_alignment=alignment,
            current_selected_position="coverage_already_complete",
            first_phase_selected_position="coverage_already_complete",
            full_coverage_selected_position="coverage_already_complete",
        )

    first_supported = evidence.first_phase.annual_comparison_yen >= 0
    full_supported = evidence.full_coverage.annual_comparison_yen >= 0
    current_position, first_position, full_position = _selected_positions(
        first_supported=first_supported,
        full_supported=full_supported,
    )
    basis: list[str] = [
        (
            "first_phase_annual_comparison_not_negative"
            if first_supported
            else "first_phase_annual_comparison_negative"
        ),
        (
            "full_coverage_annual_comparison_not_negative"
            if full_supported
            else "full_coverage_annual_comparison_negative"
        ),
    ]
    if (
        evidence.first_phase.remaining_uncovered_cow_count
        < evidence.current.remaining_uncovered_cow_count
    ):
        basis.append("first_phase_reduces_uncovered")
    if (
        evidence.full_coverage.annual_comparison_yen
        < evidence.first_phase.annual_comparison_yen
    ):
        basis.append("full_coverage_has_greater_annual_burden")

    if _full_coverage_dominates_first_phase(evidence):
        basis.append("full_coverage_dominates_first_phase")
        reading: EconomicReading = "full_coverage_dominates_first_phase"
        focus: ComparisonFocus = "full_coverage"
    elif not first_supported and not full_supported:
        reading = "additional_options_not_economically_supported"
        focus = "current_and_first_phase"
    elif first_supported and not full_supported:
        reading = "first_phase_only_economically_supported"
        focus = "first_phase_and_full_coverage"
    elif not first_supported and full_supported:
        reading = "full_coverage_only_economically_supported"
        focus = "first_phase_and_full_coverage"
    else:
        reading = "additional_options_economically_supported"
        focus = "first_phase_and_full_coverage"

    return StandardEconomicReading(
        economic_reading=reading,
        comparison_focus=focus,
        basis=tuple(basis),
        not_proven=("investment_profitability", "physical_cooling_sufficiency"),
        decision_still_belongs_to_user=True,
        declared_priority=declared_priority,
        priority_alignment=alignment,
        current_selected_position=current_position,
        first_phase_selected_position=first_position,
        full_coverage_selected_position=full_position,
    )


def build_adaptive_pathway_position(
    evidence: ThreeChoiceEvidence,
) -> AdaptivePathwayPosition:
    """Identify the next improvement pathway from deterministic evidence.

    This is deliberately narrower than an equipment recommendation.  A small
    start is positioned when it reduces the *uncovered estimate* and leaves a
    later whole-barn choice open.  A whole-barn path is positioned as
    ``COMPLETE_NOW`` only when it factually dominates the small start on every
    available comparison axis.  The calculation does not assert physical
    cooling sufficiency or investment profitability.
    """

    for option in (evidence.current, evidence.first_phase, evidence.full_coverage):
        _validate_option(option)

    current = evidence.current
    first = evidence.first_phase
    full = evidence.full_coverage

    if current.remaining_uncovered_cow_count == 0:
        return AdaptivePathwayPosition(
            overall_position="MAINTAIN",
            uncovered_change="already_covered",
            path_flexibility="not_needed",
            economic_guardrail="not_applicable",
            basis=("current_uncovered_is_zero",),
            not_proven=("physical_cooling_sufficiency", "investment_profitability"),
            decision_still_belongs_to_user=True,
        )

    first_reduces_uncovered = (
        first.remaining_uncovered_cow_count < current.remaining_uncovered_cow_count
    )
    full_reduces_uncovered = (
        full.remaining_uncovered_cow_count < current.remaining_uncovered_cow_count
    )
    first_screened = first.annual_comparison_yen >= 0
    full_screened = full.annual_comparison_yen >= 0

    if _full_coverage_dominates_first_phase(evidence) and full_reduces_uncovered:
        return AdaptivePathwayPosition(
            overall_position="COMPLETE_NOW",
            uncovered_change="complete_reduction",
            path_flexibility="not_needed",
            economic_guardrail=(
                "full_coverage_annual_comparison_not_negative"
                if full_screened
                else "full_coverage_annual_comparison_negative"
            ),
            basis=(
                "full_coverage_dominates_first_phase",
                "full_coverage_reduces_uncovered_to_zero"
                if full.remaining_uncovered_cow_count == 0
                else "full_coverage_reduces_uncovered",
                (
                    "full_coverage_annual_comparison_not_negative"
                    if full_screened
                    else "full_coverage_annual_comparison_negative"
                ),
            ),
            not_proven=("physical_cooling_sufficiency", "investment_profitability"),
            decision_still_belongs_to_user=True,
        )

    if first_reduces_uncovered:
        return AdaptivePathwayPosition(
            overall_position="START_SMALL",
            uncovered_change=(
                "complete_reduction"
                if first.remaining_uncovered_cow_count == 0
                else "partial_reduction"
            ),
            path_flexibility="high",
            economic_guardrail=(
                "first_phase_annual_comparison_not_negative"
                if first_screened
                else "first_phase_annual_comparison_negative"
            ),
            basis=tuple(
                ["first_phase_reduces_uncovered"]
                + (
                    ["full_coverage_reduces_uncovered_further"]
                    if full.remaining_uncovered_cow_count
                    < first.remaining_uncovered_cow_count
                    else []
                )
                + [
                    (
                        "first_phase_annual_comparison_not_negative"
                        if first_screened
                        else "first_phase_annual_comparison_negative"
                    )
                ]
            ),
            not_proven=("physical_cooling_sufficiency", "investment_profitability"),
            decision_still_belongs_to_user=True,
        )

    return AdaptivePathwayPosition(
        overall_position="REASSESS",
        uncovered_change="no_reduction_from_first_phase",
        path_flexibility="unclear",
        economic_guardrail=(
            "first_phase_annual_comparison_not_negative"
            if first_screened
            else "first_phase_annual_comparison_negative"
        ),
        basis=tuple(
            ["first_phase_does_not_reduce_uncovered"]
            + (["full_coverage_reduces_uncovered"] if full_reduces_uncovered else [])
            + [
                (
                    "first_phase_annual_comparison_not_negative"
                    if first_screened
                    else "first_phase_annual_comparison_negative"
                )
            ]
        ),
        not_proven=("physical_cooling_sufficiency", "investment_profitability"),
        decision_still_belongs_to_user=True,
    )

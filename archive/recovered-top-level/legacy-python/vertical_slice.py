"""Small-input deterministic investment screening for Dairy Horizon."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class ClimateYear:
    year: int
    heat_stress_days: Decimal


@dataclass(frozen=True)
class ScreeningInput:
    lactating_cows: int
    lane_count: int
    existing_fan_count: int
    milk_price_yen_per_kg: Decimal
    target_years: int


@dataclass(frozen=True)
class ScreeningAssumptions:
    cows_per_fan: int
    installed_cost_yen_per_unit_excl_tax: Decimal
    electricity_price_yen_per_kwh: Decimal
    power_kw_per_unit: Decimal
    operating_hours_per_day: Decimal
    basic_charge_yen_per_kw_month: Decimal
    inverter_reduction_ratio: Decimal
    useful_life_years: int
    variable_cost_ratio: Decimal
    consumption_tax_ratio: Decimal
    annual_interest_rate: Decimal
    capital_repayment_years: int
    max_uncovered_cow_heat_days: Decimal
    avoided_milk_loss_cases: tuple[Decimal, Decimal, Decimal]


@dataclass(frozen=True)
class ScreeningAction:
    year: int
    label_ja: str
    fan_count: int


@dataclass(frozen=True)
class ScreeningCase:
    key: str
    label_ja: str
    avoided_milk_loss_kg_per_cow_day: Decimal
    passes_target: bool
    maximum_affordable_capex_yen: Decimal
    required_avoided_milk_loss_kg_per_cow_day: Decimal | None


@dataclass(frozen=True)
class TimingOption:
    key: str
    label_ja: str
    action_summary_ja: str
    actions: tuple[ScreeningAction, ...]
    total_capex_yen_excl_tax: Decimal
    cash_required_yen_incl_tax: Decimal
    cases: tuple[ScreeningCase, ...]
    first_heat_risk_year: int | None


@dataclass(frozen=True)
class NextQuestion:
    kind: str
    question_ja: str
    action_ja: str


@dataclass(frozen=True)
class ScreeningResult:
    target_years: int
    target_end_year: int
    climate_years: tuple[ClimateYear, ...]
    standard_assumption_labels_ja: tuple[str, ...]
    timing_options: tuple[TimingOption, ...]
    next_question: NextQuestion


class ScreeningValidationError(ValueError):
    """Raised for invalid small-input screening requests."""


def required_fan_count(lactating_cows: int, lane_count: int, cows_per_fan: int) -> int:
    if lactating_cows < 1 or lane_count < 1 or cows_per_fan < 1:
        raise ScreeningValidationError("cows, lanes, and fan capacity must be positive")
    base, remainder = divmod(lactating_cows, lane_count)
    cows_by_lane = [base + (1 if index < remainder else 0) for index in range(lane_count)]
    return sum((count + cows_per_fan - 1) // cows_per_fan for count in cows_by_lane)


def _validate(inputs: ScreeningInput, assumptions: ScreeningAssumptions, climate: tuple[ClimateYear, ...]) -> None:
    if inputs.target_years not in {3, 5, 7, 10, 15, 20}:
        raise ScreeningValidationError("target years must be one of 3, 5, 7, 10, 15, or 20")
    if inputs.lane_count not in {1, 2}:
        raise ScreeningValidationError("lane count must be one or two")
    if inputs.lactating_cows < 1 or inputs.existing_fan_count < 0:
        raise ScreeningValidationError("cow count and existing fan count must be valid")
    if not ZERO <= inputs.milk_price_yen_per_kg <= Decimal("300"):
        raise ScreeningValidationError("milk price must be between 0 and 300 yen/kg")
    if not ZERO <= assumptions.variable_cost_ratio <= Decimal("0.95"):
        raise ScreeningValidationError("variable cost ratio must be between 0 and 95 percent")
    if assumptions.annual_interest_rate < ZERO or assumptions.capital_repayment_years < 1:
        raise ScreeningValidationError("interest rate and repayment years must be valid")
    if not climate:
        raise ScreeningValidationError("a climate profile is required")
    if tuple(item.year for item in climate) != tuple(sorted(item.year for item in climate)):
        raise ScreeningValidationError("climate years must be ascending")


def _active_fans(existing_fan_count: int, actions: tuple[ScreeningAction, ...], year: int) -> int:
    return existing_fan_count + sum(action.fan_count for action in actions if action.year <= year)


def _first_heat_risk_year(
    climate: tuple[ClimateYear, ...], target_end_year: int, lactating_cows: int,
    existing_fan_count: int, actions: tuple[ScreeningAction, ...], assumptions: ScreeningAssumptions,
) -> int | None:
    for annual in climate:
        if annual.year > target_end_year:
            break
        covered_cows = _active_fans(existing_fan_count, actions, annual.year) * assumptions.cows_per_fan
        uncovered_cows = max(0, lactating_cows - covered_cows)
        if Decimal(uncovered_cows) * annual.heat_stress_days > assumptions.max_uncovered_cow_heat_days:
            return annual.year
    return None


def _actions_for_start(
    start_year: int | None, climate: tuple[ClimateYear, ...], target_end_year: int,
    inputs: ScreeningInput, assumptions: ScreeningAssumptions,
) -> tuple[ScreeningAction, ...]:
    required = required_fan_count(inputs.lactating_cows, inputs.lane_count, assumptions.cows_per_fan)
    missing = max(0, required - inputs.existing_fan_count)
    if start_year is None or missing == 0 or start_year > target_end_year:
        return ()
    stage_count = (missing + 1) // 2
    stage = ScreeningAction(start_year, "第1期", stage_count)
    stage_actions = (stage,)
    risk_after_stage = _first_heat_risk_year(
        climate, target_end_year, inputs.lactating_cows, inputs.existing_fan_count, stage_actions, assumptions,
    )
    if risk_after_stage is None or stage_count == missing:
        return stage_actions
    full_year = max(start_year + 1, risk_after_stage - 1)
    if full_year > target_end_year:
        return stage_actions
    return stage_actions + (ScreeningAction(full_year, "全数整備", missing - stage_count),)


def _action_case(
    action: ScreeningAction, heat_days: Decimal, inputs: ScreeningInput,
    assumptions: ScreeningAssumptions, case_key: str, case_label: str, avoided_loss: Decimal,
) -> ScreeningCase:
    capex = assumptions.installed_cost_yen_per_unit_excl_tax * action.fan_count
    covered_cows = min(inputs.lactating_cows, action.fan_count * assumptions.cows_per_fan)
    contribution = ONE - assumptions.variable_cost_ratio
    basic = Decimal(action.fan_count) * assumptions.power_kw_per_unit * assumptions.basic_charge_yen_per_kw_month * Decimal("12")
    energy = (
        Decimal(action.fan_count) * assumptions.power_kw_per_unit * assumptions.operating_hours_per_day
        * heat_days * assumptions.electricity_price_yen_per_kwh * (ONE - assumptions.inverter_reduction_ratio)
    )
    electricity = basic + energy
    if inputs.milk_price_yen_per_kg == ZERO or covered_cows == 0 or heat_days == ZERO or contribution == ZERO:
        return ScreeningCase(case_key, case_label, avoided_loss, False, ZERO, None)
    years = assumptions.capital_repayment_years
    if assumptions.annual_interest_rate == ZERO:
        recovery_factor = ONE / Decimal(years)
    else:
        growth = (ONE + assumptions.annual_interest_rate) ** years
        recovery_factor = assumptions.annual_interest_rate * growth / (growth - ONE)
    annual_burden = capex * recovery_factor + electricity
    denominator = Decimal(covered_cows) * heat_days * inputs.milk_price_yen_per_kg * contribution
    required_loss = annual_burden / denominator
    annual_benefit = avoided_loss * denominator
    annual_net = annual_benefit - electricity
    maximum = max(ZERO, annual_net / recovery_factor)
    return ScreeningCase(
        key=case_key,
        label_ja=case_label,
        avoided_milk_loss_kg_per_cow_day=avoided_loss,
        passes_target=avoided_loss >= required_loss,
        maximum_affordable_capex_yen=maximum,
        required_avoided_milk_loss_kg_per_cow_day=required_loss,
    )


def _option(
    key: str, label_ja: str, start_year: int | None, target_end_year: int, climate: tuple[ClimateYear, ...],
    inputs: ScreeningInput, assumptions: ScreeningAssumptions,
) -> TimingOption:
    actions = _actions_for_start(start_year, climate, target_end_year, inputs, assumptions)
    by_year = {item.year: item for item in climate}
    case_keys = (("cautious", "慎重", assumptions.avoided_milk_loss_cases[0]), ("standard", "標準", assumptions.avoided_milk_loss_cases[1]), ("improved", "改善", assumptions.avoided_milk_loss_cases[2]))
    risk_year = _first_heat_risk_year(climate, target_end_year, inputs.lactating_cows, inputs.existing_fan_count, actions, assumptions)
    cases: list[ScreeningCase] = []
    for case_key, case_label, loss in case_keys:
        action_cases = tuple(_action_case(action, by_year[action.year].heat_stress_days, inputs, assumptions, case_key, case_label, loss) for action in actions)
        maximum = sum((item.maximum_affordable_capex_yen for item in action_cases), ZERO)
        required = max((item.required_avoided_milk_loss_kg_per_cow_day for item in action_cases if item.required_avoided_milk_loss_kg_per_cow_day is not None), default=None)
        cases.append(ScreeningCase(
            key=case_key, label_ja=case_label, avoided_milk_loss_kg_per_cow_day=loss,
            passes_target=risk_year is None and all(item.passes_target for item in action_cases),
            maximum_affordable_capex_yen=maximum,
            required_avoided_milk_loss_kg_per_cow_day=required,
        ))
    total = sum((assumptions.installed_cost_yen_per_unit_excl_tax * action.fan_count for action in actions), ZERO)
    summary = "、".join(f"{action.year}年に{action.label_ja}{action.fan_count}台" for action in actions) if actions else "追加投資なし"
    return TimingOption(
        key=key, label_ja=label_ja, action_summary_ja=summary, actions=actions,
        total_capex_yen_excl_tax=total,
        cash_required_yen_incl_tax=total * (ONE + assumptions.consumption_tax_ratio),
        cases=tuple(cases), first_heat_risk_year=risk_year,
    )


def _next_question(option: TimingOption, inputs: ScreeningInput) -> NextQuestion:
    statuses = [item.passes_target for item in option.cases]
    standard = option.cases[1]
    if len(set(statuses)) > 1:
        required = standard.required_avoided_milk_loss_kg_per_cow_day
        threshold = f"{required.quantize(Decimal('0.1'))}kg/頭/日" if required is not None else "必要な乳量差"
        return NextQuestion("milk_loss", f"乳量減少を防げる量が{threshold}以上なら、結論が変わる可能性があります。昨夏と春の乳量差が分かりますか？", "乳検データや出荷記録で、暑い時期と涼しい時期の乳量差を確認する")
    if inputs.milk_price_yen_per_kg == ZERO:
        return NextQuestion("milk_price", "乳価が未入力のため、回収の見込みを判断できません。現在の乳価が分かりますか？", "直近の精算書で乳価を確認する")
    payable = standard.maximum_affordable_capex_yen
    return NextQuestion("quote", f"この案が成立する目安は、設備費が約{payable.quantize(Decimal('10000')):,}円以下です。実際の見積額を確認しますか？", "設備業者へ必要台数分の見積を依頼する")


def build_screening(inputs: ScreeningInput, assumptions: ScreeningAssumptions, climate: tuple[ClimateYear, ...]) -> ScreeningResult:
    """Build a transparent, small-input screening result without detailed finance inputs."""
    _validate(inputs, assumptions, climate)
    start_year = climate[0].year
    target_end_year = start_year + inputs.target_years - 1
    available = tuple(item for item in climate if item.year <= target_end_year)
    if len(available) != inputs.target_years:
        raise ScreeningValidationError("climate profile does not cover the selected target years")
    base_risk = _first_heat_risk_year(available, target_end_year, inputs.lactating_cows, inputs.existing_fan_count, (), assumptions)
    # A safe target period is itself a useful recommendation: do not create a
    # fictional end-of-period investment merely to fill a comparison card.
    recommended_start = max(start_year, base_risk - 1) if base_risk is not None else None
    later_start = recommended_start + 3 if recommended_start is not None else start_year + 3
    options = (
        _option("now", "今から始める", start_year, target_end_year, available, inputs, assumptions),
        _option("recommended", "おすすめ時期", recommended_start, target_end_year, available, inputs, assumptions),
        _option("later", "おすすめより3年後", later_start, target_end_year, available, inputs, assumptions),
    )
    standard_assumptions = (
        "変動費率：60%（乳飼比など、売上増加に伴う費用割合）",
        "ファン導入費：1台22万円（全酪連例・税抜）",
        "電気料金：27円/kWh（標準値）",
        "防止乳量：慎重2.0／標準3.0／改善4.0kg/頭/日",
        "消費税：設備費は税抜、導入時必要資金は10%込み",
        "気候：千葉市の将来気候プロファイル",
    )
    return ScreeningResult(
        target_years=inputs.target_years, target_end_year=target_end_year, climate_years=available,
        standard_assumption_labels_ja=standard_assumptions, timing_options=options,
        next_question=_next_question(options[1], inputs),
    )

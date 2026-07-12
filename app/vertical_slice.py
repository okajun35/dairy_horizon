from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from scripts.generate_barn_layout import TieStallBarnConfig, TieStallLayoutGenerator


ROOT = Path(__file__).resolve().parents[1]
FARM_PATH = ROOT / "data/farms/chiba_60_cow_demo.json"
CLIMATE_DIR = ROOT / "data/climate_profiles"
FUTURE_CLIMATE_PATH = CLIMATE_DIR / "generated/chiba_city_2025_2034.json"

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


class InputValidationError(ValueError):
    """Raised when a submitted vertical-slice value is outside its range."""


def decimal_value(value: Any) -> Decimal:
    return Decimal(str(value))


def percent_to_ratio(value: Any) -> Decimal:
    ratio = decimal_value(value) / HUNDRED
    if not ZERO <= ratio <= ONE:
        raise InputValidationError("percentage must be between 0 and 100")
    return ratio


def display_money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}円"


def display_number(value: Decimal | None, places: str = "0.0001") -> str:
    if value is None:
        return "—"
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def load_farm_and_climate() -> tuple[dict[str, Any], dict[str, Any]]:
    farm = json.loads(FARM_PATH.read_text(encoding="utf-8"))
    climate_path = CLIMATE_DIR / f"{farm['climate_profile_id']}.json"
    climate = json.loads(climate_path.read_text(encoding="utf-8"))
    return farm, climate


def load_future_climate() -> dict[str, Any]:
    """Load the versioned profile shipped with the app; never fetch on a request."""
    return json.loads(FUTURE_CLIMATE_PATH.read_text(encoding="utf-8"))


def form_values_from_farm(farm: dict[str, Any]) -> dict[str, str]:
    return {
        "lactating_cows": str(farm["barn_input"]["lactating_cows"]),
        "lane_count": str(farm["barn_input"]["lane_count"]),
        "existing_fan_count": str(farm["barn_input"]["existing_fan_count"]),
        "milk_price_yen_per_kg": str(farm["economic_assumptions"]["milk_price_yen_per_kg"]),
        "variable_cost_ratio_pct": str(farm["economic_assumptions"]["variable_cost_ratio_pct"]),
        "avoided_milk_loss_kg_per_cow_day": str(farm["economic_assumptions"]["avoided_milk_loss_kg_per_cow_day"]),
        "electricity_price_yen_per_kwh": str(farm["economic_assumptions"]["electricity_price_yen_per_kwh"]),
        "installed_cost_yen_per_unit": str(farm["fan_assumptions"]["installed_cost_yen_per_unit"]),
        "evaluation_period_years": str(farm["evaluation_period_years"]),
        "climate_year": "2030",
        "selected_plan": "full_installation",
    }


def merge_form_values(defaults: dict[str, str], submitted: dict[str, Any] | None) -> dict[str, str]:
    if not submitted:
        return defaults
    return {key: str(submitted.get(key, defaults[key])) for key in defaults}


def calculate_required_fans(total_cows: int, lane_count: int, cows_per_fan: int) -> tuple[list[int], list[int]]:
    if total_cows < 1:
        raise InputValidationError("lactating cows must be positive")
    if lane_count not in {1, 2}:
        raise InputValidationError("lane count must be 1 or 2")
    if cows_per_fan < 1:
        raise InputValidationError("cows per target fan must be positive")
    base, remainder = divmod(total_cows, lane_count)
    cows_by_lane = [base + (1 if index < remainder else 0) for index in range(lane_count)]
    target_fans_by_lane = [(cows + cows_per_fan - 1) // cows_per_fan for cows in cows_by_lane]
    return cows_by_lane, target_fans_by_lane


def _allocate_proportionally(existing_count: int, capacities: list[int]) -> list[int]:
    total = sum(capacities)
    allocations = [(existing_count * capacity) // total for capacity in capacities]
    remainders = [existing_count * capacity % total for capacity in capacities]
    while sum(allocations) < existing_count:
        candidates = [index for index, capacity in enumerate(capacities) if allocations[index] < capacity]
        selected = max(candidates, key=lambda index: (remainders[index], -index))
        allocations[selected] += 1
    return allocations


def _even_slot_indexes(slot_count: int, fan_count: int) -> list[int]:
    if fan_count == 0:
        return []
    selected: list[int] = []
    for fan_index in range(fan_count):
        candidate = ((2 * fan_index + 1) * slot_count) // (2 * fan_count)
        if candidate in selected:
            unused = [index for index in range(slot_count) if index not in selected]
            candidate = min(unused, key=lambda index: (abs(index - candidate), index))
        selected.append(candidate)
    return selected


def allocate_existing_fans(target_fans_by_lane: list[int], existing_count: int) -> dict[int, set[int]]:
    target_count = sum(target_fans_by_lane)
    if existing_count < 0 or existing_count > target_count:
        raise InputValidationError("existing fan count must be between zero and required fan count")
    per_lane = _allocate_proportionally(existing_count, target_fans_by_lane) if existing_count else [0] * len(target_fans_by_lane)
    return {
        lane_index + 1: set(_even_slot_indexes(target_fans_by_lane[lane_index], per_lane[lane_index]))
        for lane_index in range(len(target_fans_by_lane))
    }


def allocate_stage_one_fans(target_fans_by_lane: list[int], existing_by_lane: dict[int, set[int]]) -> dict[int, set[int]]:
    missing_by_lane = {
        lane: [index for index in range(slot_count) if index not in existing_by_lane[lane]]
        for lane, slot_count in enumerate(target_fans_by_lane, start=1)
    }
    count = (sum(len(slots) for slots in missing_by_lane.values()) + 1) // 2
    selected = {lane: set() for lane in missing_by_lane}
    for _ in range(count):
        candidates = [lane for lane, slots in missing_by_lane.items() if len(selected[lane]) < len(slots)]
        if not candidates:
            break
        lane = max(candidates, key=lambda lane_id: (len(missing_by_lane[lane_id]) - len(selected[lane_id]), -lane_id))
        slot = next(slot for slot in missing_by_lane[lane] if slot not in selected[lane])
        selected[lane].add(slot)
    return selected


def calculate_newly_covered_cows(target_slots: dict[tuple[int, int], list[str]], selected_by_lane: dict[int, set[int]]) -> list[str]:
    cow_ids: set[str] = set()
    for lane, slots in selected_by_lane.items():
        for slot in slots:
            cow_ids.update(target_slots[(lane, slot)])
    return sorted(cow_ids)


@dataclass(frozen=True)
class EconomicsInputs:
    incremental_fan_count: int
    newly_covered_cow_count: int
    installed_cost_yen_per_unit: Decimal
    power_kw_per_unit: Decimal
    operating_hours_per_day: Decimal
    heat_stress_days_per_year: Decimal
    electricity_price_yen_per_kwh: Decimal
    basic_charge_yen_per_kw_month: Decimal
    inverter_reduction_ratio: Decimal
    useful_life_years: int
    evaluation_period_years: int
    milk_price_yen_per_kg: Decimal
    variable_cost_ratio: Decimal
    avoided_milk_loss_kg_per_cow_day: Decimal


def _not_applicable(plan_status: str) -> dict[str, Any]:
    return {
        "plan_status": plan_status,
        "incremental_fan_count": 0,
        "incremental_capex_yen": ZERO,
        "estimated_incremental_basic_charge_yen": ZERO,
        "incremental_energy_charge_yen": ZERO,
        "incremental_electricity_cost_yen": ZERO,
        "newly_covered_cow_count": 0,
        "break_even_status": "not_applicable",
        "break_even_reason": None,
        "break_even_milk_yield_kg_per_cow_day": None,
        "milk_yield_margin_kg_per_cow_day": None,
        "annual_contribution_benefit_yen": ZERO,
        "annual_net_benefit_yen": ZERO,
        "maximum_affordable_capex_yen": None,
        "investment_margin_yen": None,
        "preserves_requested_window": None,
        "first_failing_condition": None,
    }


def calculate_economics(inputs: EconomicsInputs, *, plan_status: str = "evaluable") -> dict[str, Any]:
    if plan_status != "evaluable":
        return _not_applicable(plan_status)

    capex = inputs.installed_cost_yen_per_unit * inputs.incremental_fan_count
    basic = inputs.incremental_fan_count * inputs.power_kw_per_unit * inputs.basic_charge_yen_per_kw_month * 12
    energy = (
        inputs.incremental_fan_count * inputs.power_kw_per_unit * inputs.operating_hours_per_day
        * inputs.heat_stress_days_per_year * inputs.electricity_price_yen_per_kwh
        * (ONE - inputs.inverter_reduction_ratio)
    )
    electricity = basic + energy
    contribution_margin = ONE - inputs.variable_cost_ratio
    annual_benefit = (
        inputs.avoided_milk_loss_kg_per_cow_day * inputs.newly_covered_cow_count
        * inputs.heat_stress_days_per_year * inputs.milk_price_yen_per_kg * contribution_margin
    )
    annual_net = annual_benefit - electricity

    reasons = (
        ("zero_milk_price", inputs.milk_price_yen_per_kg == ZERO),
        ("zero_newly_covered_cows", inputs.newly_covered_cow_count == 0),
        ("zero_heat_stress_days", inputs.heat_stress_days_per_year == ZERO),
        ("zero_contribution_margin", contribution_margin == ZERO),
    )
    reason = next((name for name, matched in reasons if matched), None)
    base = {
        "plan_status": "evaluable",
        "incremental_fan_count": inputs.incremental_fan_count,
        "incremental_capex_yen": capex,
        "estimated_incremental_basic_charge_yen": basic,
        "incremental_energy_charge_yen": energy,
        "incremental_electricity_cost_yen": electricity,
        "newly_covered_cow_count": inputs.newly_covered_cow_count,
        "annual_contribution_benefit_yen": annual_benefit,
        "annual_net_benefit_yen": annual_net,
    }
    if reason:
        return base | {
            "break_even_status": "recovery_impossible",
            "break_even_reason": reason,
            "break_even_milk_yield_kg_per_cow_day": None,
            "milk_yield_margin_kg_per_cow_day": None,
            "maximum_affordable_capex_yen": ZERO,
            "investment_margin_yen": None,
            "preserves_requested_window": False,
            "first_failing_condition": "break_even_not_calculable",
        }

    recovery_factor = ONE / inputs.evaluation_period_years
    annual_capital = capex * recovery_factor
    annual_burden = annual_capital + electricity
    denominator = (
        inputs.newly_covered_cow_count * inputs.heat_stress_days_per_year
        * inputs.milk_price_yen_per_kg * contribution_margin
    )
    break_even = annual_burden / denominator
    maximum = max(ZERO, annual_net * inputs.evaluation_period_years)
    margin = maximum - capex
    if inputs.evaluation_period_years > inputs.useful_life_years:
        failure = "evaluation_period_exceeds_useful_life"
    elif annual_net <= ZERO:
        failure = "annual_net_benefit_not_positive"
    elif maximum < capex:
        failure = "capex_not_recovered_within_evaluation_period"
    else:
        failure = None
    result = base | {
        "evaluation_period_recovery_factor": recovery_factor,
        "annual_capital_recovery_yen": annual_capital,
        "annual_burden_yen": annual_burden,
        "break_even_status": "calculable",
        "break_even_reason": None,
        "break_even_milk_yield_kg_per_cow_day": break_even,
        "milk_yield_margin_kg_per_cow_day": inputs.avoided_milk_loss_kg_per_cow_day - break_even,
        "maximum_affordable_capex_yen": maximum,
        "investment_margin_yen": margin,
        "preserves_requested_window": failure is None,
        "first_failing_condition": failure,
    }
    if failure is not None:
        required_unit_cost = maximum / inputs.incremental_fan_count
        required_avoided = break_even
        required_milk_price = annual_burden / (
            inputs.newly_covered_cow_count * inputs.heat_stress_days_per_year
            * inputs.avoided_milk_loss_kg_per_cow_day * contribution_margin
        ) if inputs.avoided_milk_loss_kg_per_cow_day > ZERO else None
        result["conditions_to_approach_feasibility"] = {
            "required_installed_cost_yen_per_unit": required_unit_cost,
            "cost_reduction_yen_per_unit": max(ZERO, inputs.installed_cost_yen_per_unit - required_unit_cost),
            "required_avoided_milk_loss_kg_per_cow_day": required_avoided,
            "additional_avoided_milk_loss_kg_per_cow_day": max(ZERO, required_avoided - inputs.avoided_milk_loss_kg_per_cow_day),
            "required_milk_price_yen_per_kg": required_milk_price,
        }
    else:
        result["conditions_to_approach_feasibility"] = None
    return result


def _inputs_from_values(
    values: dict[str, str], farm: dict[str, Any], heat_stress_days_per_year: Decimal,
) -> tuple[dict[str, Any], EconomicsInputs]:
    total_cows = int(values["lactating_cows"])
    lane_count = int(values["lane_count"])
    existing_count = int(values["existing_fan_count"])
    evaluation_years = int(values["evaluation_period_years"])
    if not 1 <= evaluation_years <= 30:
        raise InputValidationError("evaluation period must be between 1 and 30")
    layout = farm["layout_assumptions"]
    fan = farm["fan_assumptions"]
    economic = farm["economic_assumptions"]
    cows_by_lane, targets_by_lane = calculate_required_fans(total_cows, lane_count, int(layout["cows_per_target_fan"]))
    if existing_count < 0 or existing_count > sum(targets_by_lane):
        raise InputValidationError("existing fan count must be between zero and required fan count")
    common = {
        "installed_cost_yen_per_unit": decimal_value(values["installed_cost_yen_per_unit"]),
        "power_kw_per_unit": decimal_value(fan["power_kw_per_unit"]),
        "operating_hours_per_day": decimal_value(fan["operating_hours_per_day"]),
        "heat_stress_days_per_year": heat_stress_days_per_year,
        "electricity_price_yen_per_kwh": decimal_value(values["electricity_price_yen_per_kwh"]),
        "basic_charge_yen_per_kw_month": decimal_value(fan["basic_charge_yen_per_kw_month"]),
        "inverter_reduction_ratio": percent_to_ratio(fan["inverter_reduction_ratio_pct"]),
        "useful_life_years": int(fan["useful_life_years"]),
        "evaluation_period_years": evaluation_years,
        "milk_price_yen_per_kg": decimal_value(values["milk_price_yen_per_kg"]),
        "variable_cost_ratio": percent_to_ratio(values["variable_cost_ratio_pct"]),
        "avoided_milk_loss_kg_per_cow_day": decimal_value(values["avoided_milk_loss_kg_per_cow_day"]),
    }
    return {
        "total_cows": total_cows,
        "lane_count": lane_count,
        "existing_count": existing_count,
        "cows_by_lane": cows_by_lane,
        "targets_by_lane": targets_by_lane,
        "common": common,
    }, EconomicsInputs(incremental_fan_count=0, newly_covered_cow_count=0, **common)


def _selected_heat_context(
    values: dict[str, str], farm: dict[str, Any], future_climate: dict[str, Any],
) -> dict[str, Any]:
    year = values["climate_year"]
    if year == "2024":
        days = decimal_value(farm["planning_assumptions"]["heat_stress_days_per_year"])
        return {
            "selected_year": year, "heat_stress_days_median": days, "heat_stress_days_minimum": days,
            "heat_stress_days_maximum": days, "classification": "farm_demo_assumption",
            "label_ja": "基準：2024年観測と別の、全酪連年間計画例", "uses_demo_days": True,
        }
    if year not in future_climate["years"]:
        raise InputValidationError("climate year must be 2024 or a generated projection year")
    summary = future_climate["years"][year]["summary"]["thi_days_daily_mean_ge_72"]
    return {
        "selected_year": year, "heat_stress_days_median": decimal_value(summary["median"]),
        "heat_stress_days_minimum": decimal_value(summary["minimum"]),
        "heat_stress_days_maximum": decimal_value(summary["maximum"]),
        "classification": "climate_model_projection_scenario",
        "label_ja": f"将来：{year}年・複数気候モデルの中央値", "uses_demo_days": False,
    }


def build_dashboard(submitted: dict[str, Any] | None = None) -> dict[str, Any]:
    farm, climate = load_farm_and_climate()
    future_climate = load_future_climate()
    values = merge_form_values(form_values_from_farm(farm), submitted)
    heat_context = _selected_heat_context(values, farm, future_climate)
    parsed, _ = _inputs_from_values(values, farm, heat_context["heat_stress_days_median"])
    config = TieStallBarnConfig(
        lactating_cows=parsed["total_cows"],
        row_count=parsed["lane_count"],
        existing_fan_count=0,
        cows_per_fan=int(farm["layout_assumptions"]["cows_per_target_fan"]),
    )
    layout = TieStallLayoutGenerator().generate(config)
    existing_by_lane = allocate_existing_fans(parsed["targets_by_lane"], parsed["existing_count"])
    stage_one_by_lane = allocate_stage_one_fans(parsed["targets_by_lane"], existing_by_lane)
    target_slots: dict[tuple[int, int], list[str]] = {}
    fans_by_lane_slot: dict[tuple[int, int], dict[str, Any]] = {}
    lane_slot_counter = [0] * parsed["lane_count"]
    for fan in layout["fans"]:
        lane = fan["row_target"]
        slot = lane_slot_counter[lane - 1]
        lane_slot_counter[lane - 1] += 1
        cow_ids = [f"R{lane}-C{stall:03d}" for stall in fan["target_stalls"]]
        target_slots[(lane, slot)] = cow_ids
        fans_by_lane_slot[(lane, slot)] = fan
        fan["lane_id"] = lane
        fan["slot_index"] = slot
        fan["cow_ids"] = cow_ids
        fan["existing_assumed"] = slot in existing_by_lane[lane]
        fan["stage_one_selected"] = slot in stage_one_by_lane[lane]
        fan["status"] = "existing" if fan["existing_assumed"] else "needed"

    full_by_lane = {
        lane: {slot for slot in range(count) if slot not in existing_by_lane[lane]}
        for lane, count in enumerate(parsed["targets_by_lane"], start=1)
    }
    stage_one_cows = calculate_newly_covered_cows(target_slots, stage_one_by_lane)
    full_cows = calculate_newly_covered_cows(target_slots, full_by_lane)
    shortfall = len(full_cows) and sum(len(slots) for slots in full_by_lane.values())

    plans: dict[str, dict[str, Any]] = {
        "baseline": _not_applicable("comparison_only"),
    }
    for key, label, selected, cow_ids in (
        ("stage_1", "段階導入：第1期", stage_one_by_lane, stage_one_cows),
        ("full_installation", "不足ファンを全数追加", full_by_lane, full_cows),
    ):
        count = sum(len(slots) for slots in selected.values())
        status = "evaluable" if count else "no_additional_investment_required"
        economics = calculate_economics(
            EconomicsInputs(incremental_fan_count=count, newly_covered_cow_count=len(cow_ids), **parsed["common"]),
            plan_status=status,
        )
        plans[key] = economics | {"label_ja": label, "newly_covered_cow_ids": cow_ids}
    plans["baseline"] |= {"label_ja": "現状維持（baseline）", "newly_covered_cow_ids": []}

    sensitivity = build_sensitivity_rows(values, farm, heat_context["heat_stress_days_median"])
    model_range_unstable = False
    if not heat_context["uses_demo_days"]:
        for days in (heat_context["heat_stress_days_minimum"], heat_context["heat_stress_days_maximum"]):
            range_plans = _build_sensitivity_plans(values, farm, days)
            if any(
                range_plans[key]["preserves_requested_window"] != plans[key]["preserves_requested_window"]
                for key in ("stage_1", "full_installation")
            ):
                model_range_unstable = True
                break
    return {
        "farm": farm,
        "climate": climate,
        "future_climate": future_climate,
        "heat_context": heat_context,
        "model_range_unstable": model_range_unstable,
        "values": values,
        "layout": layout,
        "plans": plans,
        "target_fan_count": sum(parsed["targets_by_lane"]),
        "additional_fan_count": shortfall,
        "cows_by_lane": parsed["cows_by_lane"],
        "sensitivity": sensitivity,
        "quote_request": build_quote_request(values, plans[values["selected_plan"]]),
    }


def build_sensitivity_rows(values: dict[str, str], farm: dict[str, Any], heat_stress_days_per_year: Decimal) -> list[dict[str, Any]]:
    current = decimal_value(values["milk_price_yen_per_kg"])
    grouped: dict[Decimal, list[str]] = {}
    for label, delta in (("-20円", -20), ("-10円", -10), ("現在", 0), ("+10円", 10), ("+20円", 20)):
        price = min(Decimal("300"), max(ZERO, current + delta))
        grouped.setdefault(price, []).append(label)
    rows = []
    for price in sorted(grouped):
        updated = values | {"milk_price_yen_per_kg": str(price)}
        dashboard = _build_sensitivity_plans(updated, farm, heat_stress_days_per_year)
        rows.append({"price": price, "labels": grouped[price], "plans": dashboard})
    return rows


def _build_sensitivity_plans(
    values: dict[str, str], farm: dict[str, Any], heat_stress_days_per_year: Decimal,
) -> dict[str, dict[str, Any]]:
    parsed, _ = _inputs_from_values(values, farm, heat_stress_days_per_year)
    existing = allocate_existing_fans(parsed["targets_by_lane"], parsed["existing_count"])
    stage = allocate_stage_one_fans(parsed["targets_by_lane"], existing)
    slots: dict[tuple[int, int], list[str]] = {}
    for lane, cow_count in enumerate(parsed["cows_by_lane"], start=1):
        for slot in range(parsed["targets_by_lane"][lane - 1]):
            start = slot * int(farm["layout_assumptions"]["cows_per_target_fan"]) + 1
            end = min(cow_count, start + int(farm["layout_assumptions"]["cows_per_target_fan"]) - 1)
            slots[(lane, slot)] = [f"R{lane}-C{stall:03d}" for stall in range(start, end + 1)]
    full = {lane: {slot for slot in range(count) if slot not in existing[lane]} for lane, count in enumerate(parsed["targets_by_lane"], start=1)}
    result = {}
    for key, selected in (("stage_1", stage), ("full_installation", full)):
        cow_ids = calculate_newly_covered_cows(slots, selected)
        count = sum(len(slot_ids) for slot_ids in selected.values())
        result[key] = calculate_economics(
            EconomicsInputs(incremental_fan_count=count, newly_covered_cow_count=len(cow_ids), **parsed["common"]),
            plan_status="evaluable" if count else "no_additional_investment_required",
        )
    return result


def build_quote_request(values: dict[str, str], plan: dict[str, Any]) -> str:
    return "\n".join(
        (
            "件名：暑熱対策用送風ファンの見積依頼",
            f"対象牛群：搾乳牛 {values['lactating_cows']} 頭、{values['lane_count']} 牛床列",
            f"検討案：{plan['label_ja']}",
            f"追加ファン台数：{plan['incremental_fan_count']} 台",
            "横臥時の牛体付近で目標風速2m/s以上を満たす配置をご提案ください。",
            "見積は税込・税抜の基準を明記してください。",
            "既存ファン位置は台数から均等配置したデモ仮定のため、現地確認をお願いします。",
        )
    )

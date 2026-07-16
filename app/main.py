"""FastAPI entry point for the Dairy Horizon adaptation navigator."""

from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.climate_adjustment import (
    ClimateAdjustmentError,
    ObservationAnchoredClimateSummary,
    anchor_future_thi_days,
    load_observed_thi_baseline,
)
from app.adaptation_screening import (
    AdaptationInputError,
    TwoHorizonInput,
    build_two_horizon_screening,
)
from app.annual_heat_path import (
    AnnualHeatPathInput,
    calculate_annual_heat_path,
)
from app.climate_profile import (
    ClimatePeriodSummary,
    load_climate_profile,
    summarize_thi_days,
)
from app.financial_screening import (
    FinancialAssumptions,
    FinancialPlan,
    STANDARD_FINANCIAL_ASSUMPTIONS,
    STANDARD_USEFUL_LIFE_YEARS,
    calculate_financial_screening,
)
from app.equipment_branches import build_equipment_branches
from app.farm_sales_context import (
    FarmSalesContextInput,
    FarmSalesContextInputError,
    calculate_farm_sales_context,
)
from app.navigator import (
    BarnInput,
    CurrentBarnState,
    FanPlan,
    InputValidationError,
    build_navigation,
    guideline_fan_count,
)
from app.natural_input import (
    NaturalInputCandidate,
    NaturalInputUnavailable,
    OpenAINaturalInputInterpreter,
)
from app.pathways import build_path_comparison
from app.project_annual_economics import calculate_project_annual_economics
from app.result_explanation import (
    OpenAIResultExplainer,
    ResultExplanationUnavailable,
    build_fallback_explanation,
)


ROOT = Path(__file__).resolve().parents[1]
FUTURE_CLIMATE_PROFILE_PATH = (
    ROOT / "data/climate_profiles/generated/chiba_city_2025_2034.json"
)
BASELINE_CLIMATE_PROFILE_PATH = (
    ROOT / "data/climate_profiles/generated/chiba_city_2020_2025.json"
)
OBSERVED_THI_BASELINE_PATH = (
    ROOT / "data/observed/jma_chiba_thi_summary_2020_2025.json"
)


def _static_asset_version(relative_path: str) -> int:
    """Return a changing query value so browsers do not reuse stale assets."""
    return (ROOT / "static" / relative_path).stat().st_mtime_ns


load_dotenv(ROOT / ".env")
app = FastAPI(title="Dairy Horizon")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
templates.env.globals["static_asset_version"] = _static_asset_version
SUPPORTED_REGION_JA = "千葉市"


def get_natural_input_interpreter() -> OpenAINaturalInputInterpreter:
    """Build the API adapter without exposing credentials to route or template code."""
    return OpenAINaturalInputInterpreter(
        os.getenv("OPENAI_API_KEY", ""),
        os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
    )


def get_result_explainer() -> OpenAIResultExplainer:
    """Build the explanation adapter without exposing credentials to the UI."""

    return OpenAIResultExplainer(
        os.getenv("OPENAI_API_KEY", ""),
        os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
    )


def _optional_int(value: str | None, label_ja: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise InputValidationError(f"{label_ja}は整数で入力してください。") from exc


def _optional_bounded_int(
    value: str | None,
    label_ja: str,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    parsed = _optional_int(value, label_ja)
    if parsed is None:
        return None
    if not minimum <= parsed <= maximum:
        raise InputValidationError(
            f"{label_ja}は{minimum}〜{maximum}の整数で入力してください。"
        )
    return parsed


def _optional_operating_hours(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        hours = Decimal(value)
    except InvalidOperation as exc:
        raise InputValidationError(
            "運転時間は0〜24時間で入力してください。"
        ) from exc
    if not hours.is_finite() or hours < 0 or hours > 24:
        raise InputValidationError("運転時間は0〜24時間で入力してください。")
    return hours


def _optional_non_negative_decimal(
    value: str | None,
    label_ja: str,
) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise InputValidationError(
            f"{label_ja}は0以上の数値で入力してください。"
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise InputValidationError(
            f"{label_ja}は0以上の数値で入力してください。"
        )
    return parsed


def _format_decimal(value: Decimal) -> str:
    formatted = format(value, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted


def _format_yen(value: Decimal | None) -> str:
    if value is None:
        return "評価対象外"
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}円"


def _format_negative_yen(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        return "0円"
    return f"-{rounded:,.0f}円"


def _format_signed_yen(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if rounded > 0:
        return f"+{rounded:,.0f}円"
    return f"{rounded:,.0f}円"


def _format_milk_kg_per_cow_day(value: Decimal | None) -> str:
    if value is None:
        return "評価対象外"
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:.2f}kg／頭・日"


def _format_kg(value: Decimal | None) -> str:
    if value is None:
        return "評価対象外"
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}kg"


def _format_annual_kg(value: Decimal | None) -> str:
    if value is None:
        return "未入力"
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}kg／年"


def _rounded_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _climate_plan_view(
    plan: FanPlan,
    summary: ObservationAnchoredClimateSummary,
    assumptions: FinancialAssumptions,
    newly_covered_cow_count: int | None = None,
) -> dict[str, Any]:
    covered_cow_count = (
        len(plan.newly_covered_cow_ids)
        if newly_covered_cow_count is None
        else newly_covered_cow_count
    )
    financial_plan = FinancialPlan(
        additional_fan_count=plan.additional_fan_count,
        newly_covered_cow_count=covered_cow_count,
    )
    results = {
        key: calculate_financial_screening(
            financial_plan,
            replace(
                assumptions,
                heat_days_per_year=days,
            ),
        )
        for key, days in (
            ("minimum", summary.minimum_annual_days),
            ("median", summary.median_annual_days),
            ("maximum", summary.maximum_annual_days),
        )
    }
    break_even_values = tuple(
        result.break_even_milk_kg_per_cow_day
        for result in results.values()
        if result.break_even_milk_kg_per_cow_day is not None
    )
    return {
        "key": plan.key,
        "label_ja": plan.label_ja,
        "additional_fan_count": plan.additional_fan_count,
        "newly_covered_cow_count": covered_cow_count,
        "annual_electricity_median_yen": _rounded_int(
            results["median"].incremental_annual_electricity_cost_yen
        ),
        "annual_electricity_minimum_yen": _rounded_int(
            results["minimum"].incremental_annual_electricity_cost_yen
        ),
        "annual_electricity_maximum_yen": _rounded_int(
            results["maximum"].incremental_annual_electricity_cost_yen
        ),
        "annual_electricity_median_ja": _format_yen(
            results["median"].incremental_annual_electricity_cost_yen
        ),
        "annual_electricity_range_ja": (
            f"{_format_yen(results['minimum'].incremental_annual_electricity_cost_yen)}"
            f"〜{_format_yen(results['maximum'].incremental_annual_electricity_cost_yen)}"
        ),
        "break_even_milk_median_kg_per_cow_day": (
            float(results["median"].break_even_milk_kg_per_cow_day)
            if results["median"].break_even_milk_kg_per_cow_day is not None
            else None
        ),
        "break_even_milk_minimum_kg_per_cow_day": (
            float(min(break_even_values)) if break_even_values else None
        ),
        "break_even_milk_maximum_kg_per_cow_day": (
            float(max(break_even_values)) if break_even_values else None
        ),
    }


def _climate_period_view(
    summary: ObservationAnchoredClimateSummary,
    raw_model_summary: ClimatePeriodSummary,
    plans: tuple[FanPlan, ...],
    assumptions: FinancialAssumptions,
    covered_cow_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    hours_per_day = assumptions.operating_hours_per_day
    return {
        "key": f"{summary.start_year}_{summary.end_year}",
        "start_year": summary.start_year,
        "end_year": summary.end_year,
        "model_count": summary.model_count,
        "median_annual_days": float(summary.median_annual_days),
        "minimum_annual_days": float(summary.minimum_annual_days),
        "maximum_annual_days": float(summary.maximum_annual_days),
        "median_change_days": float(summary.median_change_days),
        "central_lower_days": float(summary.central_lower_days),
        "central_upper_days": float(summary.central_upper_days),
        "central_days_range_ja": (
            f"{_rounded_int(summary.central_lower_days)}"
            f"〜{_rounded_int(summary.central_upper_days)}日／年"
        ),
        "full_days_range_ja": (
            f"{_rounded_int(summary.minimum_annual_days)}"
            f"〜{_rounded_int(summary.maximum_annual_days)}日／年"
        ),
        "median_change_days_ja": (
            f"{summary.median_change_days:+.0f}日／年"
        ),
        "median_annual_hours": float(summary.median_annual_days * hours_per_day),
        "minimum_annual_hours": float(summary.minimum_annual_days * hours_per_day),
        "maximum_annual_hours": float(summary.maximum_annual_days * hours_per_day),
        "raw_model_median_annual_days": float(
            raw_model_summary.median_annual_days
        ),
        "raw_model_minimum_annual_days": float(
            raw_model_summary.minimum_annual_days
        ),
        "raw_model_maximum_annual_days": float(
            raw_model_summary.maximum_annual_days
        ),
        "raw_model_median_annual_days_ja": (
            f"{_rounded_int(raw_model_summary.median_annual_days)}日"
        ),
        "raw_model_annual_days_range_ja": (
            f"{_rounded_int(raw_model_summary.minimum_annual_days)}"
            f"〜{_rounded_int(raw_model_summary.maximum_annual_days)}日／年"
        ),
        "plans": tuple(
            _climate_plan_view(
                plan,
                summary,
                assumptions,
                (covered_cow_overrides or {}).get(plan.key),
            )
            for plan in plans[1:]
        ),
    }


def _climate_background(
    plans: tuple[FanPlan, ...],
    assumptions: FinancialAssumptions,
    covered_cow_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    observed = load_observed_thi_baseline(OBSERVED_THI_BASELINE_PATH)
    model_baseline = summarize_thi_days(
        load_climate_profile(BASELINE_CLIMATE_PROFILE_PATH), 2020, 2025
    )
    future_profile = load_climate_profile(FUTURE_CLIMATE_PROFILE_PATH)
    raw_future_summaries = (
        summarize_thi_days(future_profile, 2026, 2030),
        summarize_thi_days(future_profile, 2031, 2034),
    )
    if observed.thi_threshold != model_baseline.thi_threshold:
        raise ClimateAdjustmentError("観測とモデル基準のTHI閾値が一致しません。")
    adjusted_summaries = tuple(
        anchor_future_thi_days(
            observed_lower_days=observed.lower_days,
            observed_upper_days=observed.upper_days,
            model_baseline=model_baseline,
            model_future=future_summary,
        )
        for future_summary in raw_future_summaries
    )
    return {
        "available": True,
        "region_name_ja": observed.region_name_ja,
        "thi_threshold": float(observed.thi_threshold),
        "operating_hours_per_day": float(assumptions.operating_hours_per_day),
        "operating_hours_per_day_ja": _format_decimal(
            assumptions.operating_hours_per_day
        ),
        "observed_baseline": {
            "start_year": observed.start_year,
            "end_year": observed.end_year,
            "lower_annual_days": float(observed.lower_days),
            "upper_annual_days": float(observed.upper_days),
            "annual_days_range_ja": (
                f"{_rounded_int(observed.lower_days)}"
                f"〜{_rounded_int(observed.upper_days)}日／年"
            ),
            "source_publisher": observed.source_publisher,
            "source_dataset": observed.source_dataset,
        },
        "periods": tuple(
            _climate_period_view(
                adjusted,
                raw,
                plans,
                assumptions,
                covered_cow_overrides,
            )
            for adjusted, raw in zip(
                adjusted_summaries, raw_future_summaries, strict=True
            )
        ),
        "source_provider": model_baseline.source_provider,
        "source_dataset": model_baseline.source_dataset,
    }


def _financial_plan_view(
    plan: FanPlan,
    assumptions: FinancialAssumptions,
    has_user_financial_input: bool,
    newly_covered_cow_count: int | None = None,
) -> dict[str, Any]:
    covered_cow_count = (
        len(plan.newly_covered_cow_ids)
        if newly_covered_cow_count is None
        else newly_covered_cow_count
    )
    result = calculate_financial_screening(
        FinancialPlan(
            additional_fan_count=plan.additional_fan_count,
            newly_covered_cow_count=covered_cow_count,
        ),
        assumptions,
    )
    if result.status == "not_applicable":
        status_note_ja = "現在の入力では追加投資がないため、回収条件は評価対象外です。"
    elif result.reason == "zero_operating_hours":
        status_note_ja = (
            "運転時間が0時間のため、基本料金だけを表示し、回収条件は計算しません。"
        )
    elif result.status == "recovery_impossible":
        status_note_ja = "現在の標準条件では回収に必要な乳量を計算できません。"
    else:
        status_note_ja = (
            "入力した条件とその他の標準仮定による粗い比較です。"
            if has_user_financial_input
            else "標準仮定による粗い比較です。"
        ) + "牛体付近風速と夏季の防止乳量差で確認します。"
    return {
        "key": plan.key,
        "label_ja": plan.label_ja,
        "additional_fan_count": plan.additional_fan_count,
        "newly_covered_cow_count": covered_cow_count,
        "incremental_capex_yen": _rounded_int(result.incremental_capex_yen),
        "annual_electricity_yen": _rounded_int(
            result.incremental_annual_electricity_cost_yen
        ),
        "break_even_milk_kg_per_cow_day": (
            float(result.break_even_milk_kg_per_cow_day)
            if result.break_even_milk_kg_per_cow_day is not None
            else None
        ),
        "incremental_capex_ja": _format_yen(result.incremental_capex_yen),
        "annual_electricity_ja": _format_yen(
            result.incremental_annual_electricity_cost_yen
        ),
        "break_even_milk_ja": _format_milk_kg_per_cow_day(
            result.break_even_milk_kg_per_cow_day
        ),
        "maximum_affordable_capex_ja": _format_yen(
            result.maximum_affordable_capex_yen
        ),
        "investment_margin_ja": _format_yen(result.investment_margin_yen),
        "status_note_ja": status_note_ja,
    }


def _financial_comparison(
    plans: tuple[FanPlan, ...],
    assumptions: FinancialAssumptions,
    input_source_kinds: dict[str, str],
    covered_cow_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    has_user_financial_input = "user_input" in input_source_kinds.values()
    return {
        "plans": tuple(
            _financial_plan_view(
                plan,
                assumptions,
                has_user_financial_input,
                (covered_cow_overrides or {}).get(plan.key),
            )
            for plan in plans[1:]
        ),
        "assumptions": (
            {
                "label": "1台あたり設備費",
                "value": _format_yen(assumptions.installed_cost_yen_per_fan),
                "kind": "industry_guidance",
            },
            {
                "label": "消費電力",
                "value": f"{assumptions.power_kw_per_fan}kW／台",
                "kind": "industry_guidance",
            },
            {
                "label": "暑い日の平均運転時間",
                "value": f"{_format_decimal(assumptions.operating_hours_per_day)}時間／日",
                "kind": input_source_kinds["operating_hours_per_day"],
            },
            {
                "label": "標準の暑熱対策日数",
                "value": f"{_format_decimal(assumptions.heat_days_per_year)}日／年",
                "kind": "industry_guidance",
            },
            {
                "label": "電力量単価",
                "value": f"{assumptions.electricity_price_yen_per_kwh}円／kWh",
                "kind": input_source_kinds["electricity_price_yen_per_kwh"],
            },
            {
                "label": "基本料金単価",
                "value": f"{assumptions.basic_charge_yen_per_kw_month:,}円／kW・月",
                "kind": "industry_guidance",
            },
            {
                "label": "インバーター削減率",
                "value": (
                    f"{(assumptions.inverter_reduction_ratio * 100).quantize(Decimal('1'))}%"
                ),
                "kind": "industry_guidance",
            },
            {
                "label": "法定耐用年数",
                "value": f"{assumptions.useful_life_years}年",
                "kind": "industry_guidance",
            },
            {
                "label": "変動費率",
                "value": (
                    f"{(assumptions.variable_cost_ratio * 100).quantize(Decimal('1'))}%"
                ),
                "kind": "industry_guidance",
            },
            {
                "label": "実現乳価",
                "value": f"{assumptions.milk_price_yen_per_kg}円／kg",
                "kind": input_source_kinds["milk_price_yen_per_kg"],
            },
            {
                "label": "夏季の防止乳量差",
                "value": (
                    f"{assumptions.avoided_milk_loss_kg_per_cow_day}kg／頭・日"
                ),
                "kind": input_source_kinds[
                    "avoided_milk_loss_kg_per_cow_day"
                ],
            },
        ),
    }


def _annual_recovery_snapshot(
    *,
    label_ja: str,
    period_ja: str,
    plan: FanPlan,
    covered_cow_count: int,
    heat_days_per_year: Decimal,
    assumptions: FinancialAssumptions,
) -> dict[str, Any]:
    """Build one annual view while keeping equipment and coverage fixed."""

    financial_plan = FinancialPlan(
        additional_fan_count=plan.additional_fan_count,
        newly_covered_cow_count=covered_cow_count,
    )
    period_assumptions = replace(
        assumptions,
        heat_days_per_year=heat_days_per_year,
    )
    result = calculate_financial_screening(financial_plan, period_assumptions)
    economics = calculate_project_annual_economics(
        financial_plan, period_assumptions
    )
    return {
        "label_ja": label_ja,
        "period_ja": period_ja,
        "heat_days_per_year": float(heat_days_per_year),
        "heat_days_per_year_ja": (
            f"{heat_days_per_year.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}日／年"
        ),
        "annual_electricity_yen": _rounded_int(
            result.incremental_annual_electricity_cost_yen
        ),
        "annual_electricity_ja": _format_yen(
            result.incremental_annual_electricity_cost_yen
        ),
        "annual_avoided_milk_ja": _format_kg(
            economics.annual_avoided_milk_kg
        ),
        "annual_gross_milk_value_ja": _format_yen(
            economics.annual_gross_milk_value_yen
        ),
        "annual_contribution_benefit_ja": _format_yen(
            economics.annual_contribution_benefit_yen
        ),
        "annualized_capex_ja": _format_yen(economics.annualized_capex_yen),
        "annual_project_burden_ja": _format_yen(
            economics.annual_project_burden_yen
        ),
        "annual_project_balance_ja": _format_yen(
            economics.annual_project_balance_yen
        ),
        "annual_project_balance_yen": (
            float(economics.annual_project_balance_yen)
            if economics.annual_project_balance_yen is not None
            else None
        ),
        "break_even_milk_kg_per_cow_day": (
            float(result.break_even_milk_kg_per_cow_day)
            if result.break_even_milk_kg_per_cow_day is not None
            else None
        ),
        "break_even_milk_ja": _format_milk_kg_per_cow_day(
            result.break_even_milk_kg_per_cow_day
        ),
    }


def _two_horizon_financial_view(
    *,
    first_phase_plan: FanPlan,
    covered_cow_count: int,
    assumptions: FinancialAssumptions,
    climate_background: dict[str, Any],
    future_target_cow_count: int | None,
) -> dict[str, Any] | None:
    """Compare annual recovery conditions at two climate snapshots.

    This deliberately does not interpolate herd size or calculate cumulative
    ROI. Climate changes only the annual heat-day assumption.
    """

    if future_target_cow_count is None:
        return None

    observed = climate_background["observed_baseline"]
    current_heat_days = (
        Decimal(str(observed["lower_annual_days"]))
        + Decimal(str(observed["upper_annual_days"]))
    ) / Decimal("2")
    future_period = climate_background["periods"][-1]
    future_heat_days = Decimal(str(future_period["median_annual_days"]))

    return {
        "current": _annual_recovery_snapshot(
            label_ja="現在条件での年間回収目安",
            period_ja=(
                f"JMA実績 {observed['start_year']}〜{observed['end_year']}年"
            ),
            plan=first_phase_plan,
            covered_cow_count=covered_cow_count,
            heat_days_per_year=current_heat_days,
            assumptions=assumptions,
        ),
        "future": _annual_recovery_snapshot(
            label_ja="5年後条件での年間回収目安",
            period_ja=(
                f"CMIP6参考 {future_period['start_year']}〜"
                f"{future_period['end_year']}年"
            ),
            plan=first_phase_plan,
            covered_cow_count=covered_cow_count,
            heat_days_per_year=future_heat_days,
            assumptions=assumptions,
        ),
        "additional_fan_count": first_phase_plan.additional_fan_count,
        "covered_cow_count": covered_cow_count,
    }


def _annual_heat_path_comparison_view(
    *,
    plans: tuple[FanPlan, ...],
    initial_uncovered_cow_count: int,
    assumptions: FinancialAssumptions,
    climate_background: dict[str, Any],
    covered_cow_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Compare each current-period plan with the same no-action baseline."""

    observed = climate_background["observed_baseline"]
    heat_days_per_year = (
        Decimal(str(observed["lower_annual_days"]))
        + Decimal(str(observed["upper_annual_days"]))
    ) / Decimal("2")
    milk_loss = assumptions.avoided_milk_loss_kg_per_cow_day or Decimal("0")
    period_assumptions = replace(
        assumptions,
        heat_days_per_year=heat_days_per_year,
    )

    plan_views: list[dict[str, Any]] = []
    for plan in plans:
        newly_covered_cow_count = min(
            initial_uncovered_cow_count,
            (covered_cow_overrides or {}).get(
                plan.key, len(plan.newly_covered_cow_ids)
            ),
        )
        financial = calculate_financial_screening(
            FinancialPlan(
                additional_fan_count=plan.additional_fan_count,
                newly_covered_cow_count=newly_covered_cow_count,
            ),
            period_assumptions,
        )
        result = calculate_annual_heat_path(
            AnnualHeatPathInput(
                initial_uncovered_cow_count=initial_uncovered_cow_count,
                newly_covered_cow_count=newly_covered_cow_count,
                heat_days_per_year=heat_days_per_year,
                milk_loss_kg_per_cow_day=milk_loss,
                milk_price_yen_per_kg=assumptions.milk_price_yen_per_kg,
                variable_cost_ratio=assumptions.variable_cost_ratio,
                annual_project_burden_yen=financial.annual_burden_yen,
            )
        )
        improvement = result.improvement_vs_no_action_yen
        if plan.key == "current":
            improvement_class = "annual-path-improvement-neutral"
            status_note_ja = "何もしない場合の基準"
        elif improvement > 0:
            improvement_class = "annual-path-improvement-positive"
            status_note_ja = "何もしない場合より改善"
        else:
            improvement_class = "annual-path-improvement-negative"
            status_note_ja = "設備負担が防げる限界利益を上回る"
        plan_views.append(
            {
                "key": plan.key,
                "label_ja": "追加なし" if plan.key == "current" else plan.label_ja,
                "remaining_uncovered_cow_count": (
                    result.remaining_uncovered_cow_count
                ),
                "remaining_milk_loss_kg": float(
                    result.remaining_milk_loss_kg
                ),
                "remaining_gross_milk_loss_yen": _rounded_int(
                    result.remaining_gross_milk_loss_yen
                ),
                "annual_project_burden_yen": _rounded_int(
                    result.annual_project_burden_yen
                ),
                "improvement_vs_no_action_yen": _rounded_int(improvement),
                "remaining_milk_loss_ja": _format_kg(
                    result.remaining_milk_loss_kg
                ),
                "remaining_gross_milk_loss_ja": _format_negative_yen(
                    result.remaining_gross_milk_loss_yen
                ),
                "annual_project_burden_ja": _format_negative_yen(
                    result.annual_project_burden_yen
                ),
                "improvement_vs_no_action_ja": _format_signed_yen(
                    improvement
                ),
                "improvement_class": improvement_class,
                "status_note_ja": status_note_ja,
            }
        )

    return {
        "heat_days_per_year": float(heat_days_per_year),
        "heat_days_per_year_ja": (
            f"{heat_days_per_year.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}日／年"
        ),
        "plans": tuple(plan_views),
    }


def _equipment_branch_views(
    *,
    standard_fan_count: int,
    standard_covered_cow_count: int,
    assumptions: FinancialAssumptions,
    standard_coverage_confirmed: bool,
) -> tuple[dict[str, Any], ...]:
    branches = build_equipment_branches(
        standard_fan_count=standard_fan_count,
        standard_covered_cow_count=standard_covered_cow_count,
        assumptions=assumptions,
        standard_coverage_confirmed=standard_coverage_confirmed,
    )
    return tuple(
        {
            "key": branch.key,
            "label_ja": branch.label_ja,
            "planned_fan_count": branch.planned_fan_count,
            "power_kw_per_fan_ja": _format_decimal(branch.power_kw_per_fan),
            "power_source_kind": branch.power_source_kind,
            "count_source_kind": branch.count_source_kind,
            "coverage_note_ja": (
                f"実測で確認した{branch.covered_cow_count}頭を使用"
                if branch.coverage_status == "confirmed_measurement"
                else (
                    f"頭数基準による新規カバー想定{branch.covered_cow_count}頭"
                    if branch.coverage_status == "guidance_estimate"
                    else "必要台数とカバー範囲は未評価"
                )
            ),
            "annual_electricity_ja": _format_yen(
                branch.annual_electricity_yen
            ),
            "incremental_capex_ja": _format_yen(
                branch.incremental_capex_yen
            ),
            "break_even_milk_ja": _format_milk_kg_per_cow_day(
                branch.break_even_milk_kg_per_cow_day
            ),
            "next_confirmation_ja": branch.next_confirmation_ja,
        }
        for branch in branches
    )


def _result_explanation_payload(dashboard: dict[str, Any]) -> dict[str, Any]:
    """Build the only numeric contract sent to the explanation API."""

    navigation = dashboard["navigation"]
    current = navigation.current_state
    financial_by_key = {
        plan["key"]: plan for plan in dashboard["financial_comparison"]["plans"]
    }
    plans: list[dict[str, Any]] = []
    for plan in navigation.plans[1:]:
        financial = financial_by_key[plan.key]
        climate_periods: list[dict[str, Any]] = []
        for period in dashboard["climate_background"]["periods"]:
            climate_plan = next(
                item for item in period["plans"] if item["key"] == plan.key
            )
            climate_periods.append(
                {
                    "start_year": period["start_year"],
                    "end_year": period["end_year"],
                    "annual_electricity_median_yen": climate_plan[
                        "annual_electricity_median_yen"
                    ],
                    "annual_electricity_minimum_yen": climate_plan[
                        "annual_electricity_minimum_yen"
                    ],
                    "annual_electricity_maximum_yen": climate_plan[
                        "annual_electricity_maximum_yen"
                    ],
                    "break_even_milk_median_kg_per_cow_day": climate_plan[
                        "break_even_milk_median_kg_per_cow_day"
                    ],
                    "break_even_milk_minimum_kg_per_cow_day": climate_plan[
                        "break_even_milk_minimum_kg_per_cow_day"
                    ],
                    "break_even_milk_maximum_kg_per_cow_day": climate_plan[
                        "break_even_milk_maximum_kg_per_cow_day"
                    ],
                }
            )
        plans.append(
            {
                "key": plan.key,
                "label_ja": plan.label_ja,
                "additional_fan_count": plan.additional_fan_count,
                "newly_covered_cow_count": len(plan.newly_covered_cow_ids),
                "remaining_uncovered_cow_count": (
                    navigation.inputs.lactating_cows - len(plan.covered_cow_ids)
                ),
                "capex_yen": financial["incremental_capex_yen"],
                "standard_annual_electricity_yen": financial[
                    "annual_electricity_yen"
                ],
                "standard_break_even_milk_kg_per_cow_day": financial[
                    "break_even_milk_kg_per_cow_day"
                ],
                "climate_periods": climate_periods,
            }
        )

    climate = dashboard["climate_background"]
    adaptation = dashboard["two_horizon_screening"]
    annual_heat_path = dashboard["annual_heat_path_comparison"]
    return {
        "input": {
            "region_ja": navigation.inputs.region_ja,
            "lactating_cows": navigation.inputs.lactating_cows,
            "lane_count": navigation.inputs.lane_count,
            "existing_fan_count": navigation.inputs.existing_fan_count,
            "reference_mode": dashboard["input_mode"] == "guideline_reference",
            "operating_hours_per_day": dashboard["operating_hours"]["value"],
            "operating_hours_source_kind": dashboard["operating_hours"][
                "source_kind"
            ],
        },
        "current": {
            "guideline_fan_count": current.guideline_fan_count,
            "fan_shortage": current.guideline_gap_fan_count,
            "uncovered_cow_count": len(current.estimated_uncovered_cow_ids),
        },
        "future": (
            {
                "horizon_years": adaptation.inputs.horizon_years,
                "target_cow_count": adaptation.future_after.target_cow_count,
                "active_fan_count": adaptation.future_after.active_fan_count,
                "guideline_fan_count": adaptation.future_after.guideline_fan_count,
                "guideline_gap_fan_count": adaptation.future_after.guideline_gap_fan_count,
            }
            if adaptation.future_after is not None
            else None
        ),
        "decision_context": {
            "coverage_status": adaptation.coverage_status,
            "assumed_newly_covered_cow_count": (
                adaptation.assumed_newly_covered_cow_count
            ),
            "covered_cow_count_for_finance": (
                adaptation.covered_cow_count_for_finance
            ),
            "next_check_key": adaptation.next_check_key,
        },
        "plans": plans,
        "annual_heat_path": {
            "heat_days_per_year": annual_heat_path["heat_days_per_year"],
            "plans": tuple(
                {
                    "key": plan["key"],
                    "remaining_uncovered_cow_count": plan[
                        "remaining_uncovered_cow_count"
                    ],
                    "remaining_milk_loss_kg": plan[
                        "remaining_milk_loss_kg"
                    ],
                    "remaining_gross_milk_loss_yen": plan[
                        "remaining_gross_milk_loss_yen"
                    ],
                    "annual_project_burden_yen": plan[
                        "annual_project_burden_yen"
                    ],
                    "improvement_vs_no_action_yen": plan[
                        "improvement_vs_no_action_yen"
                    ],
                }
                for plan in annual_heat_path["plans"]
            ),
        },
        "climate": {
            "region_name_ja": climate["region_name_ja"],
            "thi_threshold": climate["thi_threshold"],
            "operating_hours_per_day": climate["operating_hours_per_day"],
            "observed_baseline": climate["observed_baseline"],
            "periods": tuple(
                {
                    "start_year": period["start_year"],
                    "end_year": period["end_year"],
                    "model_count": period["model_count"],
                    "median_change_days": period["median_change_days"],
                    "central_lower_days": period["central_lower_days"],
                    "central_upper_days": period["central_upper_days"],
                    "median_annual_days": period["median_annual_days"],
                    "minimum_annual_days": period["minimum_annual_days"],
                    "maximum_annual_days": period["maximum_annual_days"],
                    "raw_model_median_annual_days": period[
                        "raw_model_median_annual_days"
                    ],
                    "raw_model_minimum_annual_days": period[
                        "raw_model_minimum_annual_days"
                    ],
                    "raw_model_maximum_annual_days": period[
                        "raw_model_maximum_annual_days"
                    ],
                }
                for period in climate["periods"]
            ),
        },
        "boundaries": {
            "climate_changes_fan_count": False,
            "recommend_investment_year": False,
            "climate_data_end_year": 2034,
            "unavailable_after_end_year": True,
        },
    }


def _result_facts_ja(payload: dict[str, Any]) -> tuple[str, ...]:
    current = payload["current"]
    first_phase = payload["plans"][0]
    observed = payload["climate"]["observed_baseline"]
    near_future = payload["climate"]["periods"][0]
    operating_hours = Decimal(str(payload["input"]["operating_hours_per_day"]))
    if first_phase["additional_fan_count"]:
        plan_fact = (
            f"第1期は{first_phase['additional_fan_count']}台追加で"
            f"{first_phase['newly_covered_cow_count']}頭を新たにカバーし、"
            f"導入費は{first_phase['capex_yen']:,}円です。"
        )
    else:
        plan_fact = "現在の入力では、第1期の追加投資はありません。"
    return (
        f"現在は頭数目安より{current['fan_shortage']}台少なく、"
        f"未カバー推計は{current['uncovered_cow_count']}頭です。",
        plan_fact,
        f"日平均THI {payload['climate']['thi_threshold']:.0f}以上の日数は、"
        f"現在相当は{_rounded_int(Decimal(str(observed['lower_annual_days'])))}"
        f"〜{_rounded_int(Decimal(str(observed['upper_annual_days'])))}日／年です。",
        f"暑い日の平均運転時間は{_format_decimal(operating_hours)}時間／日です。",
        f"{near_future['start_year']}〜{near_future['end_year']}年の暑熱対象日は"
        f"中心目安{_rounded_int(Decimal(str(near_future['central_lower_days'])))}"
        f"〜{_rounded_int(Decimal(str(near_future['central_upper_days'])))}日、"
        f"モデル差を含む範囲{_rounded_int(Decimal(str(near_future['minimum_annual_days'])))}"
        f"〜{_rounded_int(Decimal(str(near_future['maximum_annual_days'])))}日／年です。",
    )


def _evidence(
    inputs: BarnInput,
    current_state: CurrentBarnState,
    first_phase_fan_count: int,
    financial_assumptions: FinancialAssumptions,
    input_source_kinds: dict[str, str],
    *,
    reference_mode: bool = False,
    future_target_cow_count: int | None = None,
    confirmed_covered_cow_count: int | None = None,
    current_annual_shipped_milk_kg: Decimal | None = None,
    future_annual_shipped_milk_kg: Decimal | None = None,
) -> tuple[dict[str, str], ...]:
    reference_uses_guideline = (
        inputs.existing_fan_count == current_state.guideline_fan_count
    )
    reference_kind = "industry_guidance" if reference_uses_guideline else "user_input"
    reference_source = (
        "頭数基準の台数目安を参考状態として使用"
        if reference_uses_guideline
        else "利用者が参考状態として変更"
    )
    assumed_by_lane = " ／ ".join(
        f"第{index}牛床列 {count}台"
        for index, count in enumerate(current_state.assumed_existing_fans_by_lane, start=1)
    )
    input_rows = (
        (
            {"item": "搾乳牛頭数・牛床列数", "value": f"{inputs.lactating_cows}頭・{inputs.lane_count}列", "kind": "user_input", "source": "今回の入力", "note": "結果を更新すると反映されます。"},
            {"item": "現在のファン数", "value": "未確認", "kind": "user_input", "source": "今回の入力に記載なし", "note": "参考配置とは区別しています。"},
            {"item": "参考配置", "value": f"{inputs.existing_fan_count}台", "kind": reference_kind, "source": reference_source, "note": f"参考状態として目安との差{current_state.guideline_gap_fan_count}台を評価しています。現在ある台数ではありません。"},
        )
        if reference_mode
        else (
            {"item": "搾乳牛頭数・牛床列数・既存ファン数", "value": f"{inputs.lactating_cows}頭・{inputs.lane_count}列・{inputs.existing_fan_count}台", "kind": "user_input", "source": "今回の入力", "note": "結果を更新すると反映されます。"},
        )
    )
    comparison_rows = (
        (
            {"item": "参考状態の総台数", "value": f"{inputs.existing_fan_count}台", "kind": reference_kind, "source": reference_source, "note": "現在ある台数ではなく、増減して比較できる参考状態です。"},
            {"item": "参考ファンの仮配置", "value": assumed_by_lane, "kind": current_state.placement_basis_kind, "source": "牛床列へ均等配置した画面表示用の仮定", "note": current_state.placement_note_ja},
            {"item": "参考比較の計画総台数", "value": f"{inputs.planned_fan_count if inputs.planned_fan_count is not None else current_state.guideline_fan_count}台", "kind": "user_input" if inputs.planned_fan_count is not None else "industry_guidance", "source": "利用者が参考比較用に入力" if inputs.planned_fan_count is not None else "未入力のため頭数基準を使用", "note": f"参考配置{inputs.existing_fan_count}台との差分を比較します。現在の設備計画ではありません。"},
            {"item": "参考比較の第1期", "value": f"{first_phase_fan_count}台", "kind": "demo_assumption", "source": "段階導入を比較するためのモデルケース", "note": "推奨台数ではなく、結果画面で変更できます。"},
        )
        if reference_mode
        else (
            {"item": "今回の計画総台数", "value": f"{inputs.planned_fan_count if inputs.planned_fan_count is not None else current_state.guideline_fan_count}台", "kind": "user_input" if inputs.planned_fan_count is not None else "industry_guidance", "source": "利用者入力" if inputs.planned_fan_count is not None else "未入力のため頭数基準を使用", "note": f"既存{inputs.existing_fan_count}台との差分を、今回追加する台数として比較します。"},
            {"item": "既存ファンの仮配置", "value": assumed_by_lane, "kind": current_state.placement_basis_kind, "source": "牛床列へ均等配置した画面表示用の仮定", "note": current_state.placement_note_ja},
            {"item": "第1期の比較台数", "value": f"{first_phase_fan_count}台", "kind": "demo_assumption", "source": "段階導入を比較するための初期モデルケース", "note": "推奨台数ではありません。結果画面で変更できます。"},
        )
    )
    future_rows = (
        (
            {
                "item": "5年後の対策対象頭数",
                "value": f"{future_target_cow_count}頭",
                "kind": "user_input",
                "source": "今回の入力",
                "note": "現在の頭数と混ぜず、5年後の頭数基準だけに使用します。",
            },
        )
        if future_target_cow_count is not None
        else ()
    )
    measurement_rows = (
        (
            {
                "item": "実測で条件を満たしたカバー頭数",
                "value": f"{confirmed_covered_cow_count}頭",
                "kind": "user_input",
                "source": "牛体付近風速の確認結果",
                "note": "回収計算の対象頭数へ使用します。乳量効果の確認ではありません。",
            },
        )
        if confirmed_covered_cow_count is not None
        else ()
    )
    shipment_rows = tuple(
        row
        for row in (
            (
                {
                    "item": "現在の年間出荷乳量",
                    "value": _format_annual_kg(current_annual_shipped_milk_kg),
                    "kind": "user_input",
                    "source": "今回の入力",
                    "note": "実現乳価との積を売上規模の背景にだけ使用します。",
                }
                if current_annual_shipped_milk_kg is not None
                else None
            ),
            (
                {
                    "item": "5年後の年間出荷乳量",
                    "value": _format_annual_kg(future_annual_shipped_milk_kg),
                    "kind": "user_input",
                    "source": "今回の入力",
                    "note": "現在値や頭数から推定せず、直接入力された場合だけ表示します。",
                }
                if future_annual_shipped_milk_kg is not None
                else None
            ),
        )
        if row is not None
    )
    return input_rows + future_rows + measurement_rows + shipment_rows + (
        {"item": "ファンのカバー目安", "value": "3頭／台・牛体付近2m/s以上", "kind": current_state.coverage_basis_kind, "source": "全酪連 COW BELL No.178『暑熱対策の設備投資を考える』pp.6-8", "note": "実際の間隔・風量・設置位置で必ず確認します。"},
        {"item": "頭数基準の台数目安", "value": f"{current_state.guideline_fan_count}台", "kind": "industry_guidance", "source": "搾乳牛頭数を3頭／台で割り、全体で切り上げ", "note": "投資試算用の目安です。列数による自動補正は行いません。"},
        {"item": "法定耐用年数", "value": f"{STANDARD_USEFUL_LIFE_YEARS}年", "kind": "industry_guidance", "source": "全酪連 COW BELL No.178の標準計算例", "note": "採算計算の年割りに使います。実際の故障年や交換年ではありません。"},
        {"item": "暑い日の平均運転時間", "value": f"{_format_decimal(financial_assumptions.operating_hours_per_day)}時間／日", "kind": input_source_kinds["operating_hours_per_day"], "source": "利用者が結果画面で入力" if input_source_kinds["operating_hours_per_day"] == "user_input" else "全酪連標準計算例", "note": "電力量と回収条件に使用します。THI対象日数、ファン台数、設備費、投資年は変更しません。"},
        {"item": "夏季の防止乳量差", "value": f"{_format_decimal(financial_assumptions.avoided_milk_loss_kg_per_cow_day or Decimal('0'))}kg／頭・日", "kind": input_source_kinds["avoided_milk_loss_kg_per_cow_day"], "source": "利用者入力" if input_source_kinds["avoided_milk_loss_kg_per_cow_day"] == "user_input" else "比較用デモ仮定", "note": "設備効果の保証値ではなく、年間便益と払える目安へ使用します。"},
        {"item": "実現乳価", "value": f"{_format_decimal(financial_assumptions.milk_price_yen_per_kg)}円／kg", "kind": input_source_kinds["milk_price_yen_per_kg"], "source": "利用者入力" if input_source_kinds["milk_price_yen_per_kg"] == "user_input" else "全酪連標準計算例", "note": "年間便益と回収に必要な防止乳量へ使用します。"},
        {"item": "電力量単価", "value": f"{_format_decimal(financial_assumptions.electricity_price_yen_per_kwh)}円／kWh", "kind": input_source_kinds["electricity_price_yen_per_kwh"], "source": "利用者入力" if input_source_kinds["electricity_price_yen_per_kwh"] == "user_input" else "全酪連標準計算例", "note": "追加ファンの年間電気代へ使用します。"},
        {"item": "省電力100cm級の比較仕様", "value": "0.25kW／台・標準型と同じ台数", "kind": "manufacturer_spec", "source": "利用者提供『乳牛の暑熱対策チャレンジ ガイドブックin十勝』資材一覧", "note": "台数は比較用デモ仮定です。カバー範囲と回収条件は未評価です。"},
        {"item": "大型高風量型の比較仕様", "value": "1.055kW／台・2台", "kind": "manufacturer_spec", "source": "利用者提供『乳牛の暑熱対策チャレンジ ガイドブックin十勝』資材一覧", "note": "2台は比較用デモ仮定です。必要台数とカバー範囲は未評価です。"},
    ) + comparison_rows + (
        {"item": "直近の暑熱対象日", "value": "2020〜2025年の年平均97.0〜97.5日", "kind": "official_observation", "source": "気象庁『過去の気象データ検索』千葉（観測点47682）", "note": "日平均THI 72以上。湿度欠測3日を非暑熱日とせず下限・上限で保持しています。"},
        {"item": "将来気候", "value": "2026〜2034年を観測基準へ補正して期間表示", "kind": "processed_cmip6_api", "source": "Open-Meteo Climate API・CMIP6共通6モデルの保存済みプロファイル", "note": "モデルごとに将来期間−2020〜2025年モデル基準を計算し、気象庁観測基準へ加えます。ファン台数・投資時期には使いません。"},
    )


def _dashboard(
    lactating_cows: int,
    lane_count: int,
    existing_fan_count: int,
    first_phase_fan_count: int | None,
    investment_year: int,
    planned_fan_count: int | None = None,
    region_ja: str = SUPPORTED_REGION_JA,
    reference_mode: bool = False,
    operating_hours_per_day: Decimal | None = None,
    future_target_cow_count: int | None = None,
    confirmed_covered_cow_count: int | None = None,
    avoided_milk_loss_kg_per_cow_day: Decimal | None = None,
    milk_price_yen_per_kg: Decimal | None = None,
    electricity_price_yen_per_kwh: Decimal | None = None,
    current_annual_shipped_milk_kg: Decimal | None = None,
    future_annual_shipped_milk_kg: Decimal | None = None,
) -> dict[str, Any]:
    inputs = BarnInput(
        lactating_cows=lactating_cows,
        lane_count=lane_count,
        existing_fan_count=existing_fan_count,
        first_phase_fan_count=first_phase_fan_count,
        planned_fan_count=planned_fan_count,
        region_ja=region_ja,
    )
    navigation = build_navigation(inputs)
    path_comparison = build_path_comparison(inputs, investment_year=investment_year)
    two_horizon_screening = build_two_horizon_screening(
        TwoHorizonInput(
            current_target_cow_count=lactating_cows,
            future_target_cow_count=future_target_cow_count,
            existing_fan_count=existing_fan_count,
            first_phase_additional_fan_count=(
                navigation.plans[1].additional_fan_count
            ),
            horizon_years=5,
            confirmed_covered_cow_count=confirmed_covered_cow_count,
        )
    )
    covered_cow_overrides = (
        {"first_phase": two_horizon_screening.covered_cow_count_for_finance}
        if confirmed_covered_cow_count is not None
        else None
    )
    hours_were_entered = operating_hours_per_day is not None
    effective_operating_hours = (
        operating_hours_per_day
        if operating_hours_per_day is not None
        else STANDARD_FINANCIAL_ASSUMPTIONS.operating_hours_per_day
    )
    operating_hours_source_kind = (
        "user_input" if hours_were_entered else "industry_guidance"
    )
    input_source_kinds = {
        "operating_hours_per_day": operating_hours_source_kind,
        "avoided_milk_loss_kg_per_cow_day": (
            "user_input"
            if avoided_milk_loss_kg_per_cow_day is not None
            else "demo_assumption"
        ),
        "milk_price_yen_per_kg": (
            "user_input"
            if milk_price_yen_per_kg is not None
            else "industry_guidance"
        ),
        "electricity_price_yen_per_kwh": (
            "user_input"
            if electricity_price_yen_per_kwh is not None
            else "industry_guidance"
        ),
    }
    financial_assumptions = replace(
        STANDARD_FINANCIAL_ASSUMPTIONS,
        operating_hours_per_day=effective_operating_hours,
        avoided_milk_loss_kg_per_cow_day=(
            avoided_milk_loss_kg_per_cow_day
            if avoided_milk_loss_kg_per_cow_day is not None
            else STANDARD_FINANCIAL_ASSUMPTIONS.avoided_milk_loss_kg_per_cow_day
        ),
        milk_price_yen_per_kg=(
            milk_price_yen_per_kg
            if milk_price_yen_per_kg is not None
            else STANDARD_FINANCIAL_ASSUMPTIONS.milk_price_yen_per_kg
        ),
        electricity_price_yen_per_kwh=(
            electricity_price_yen_per_kwh
            if electricity_price_yen_per_kwh is not None
            else STANDARD_FINANCIAL_ASSUMPTIONS.electricity_price_yen_per_kwh
        ),
    )
    farm_sales_context = calculate_farm_sales_context(
        FarmSalesContextInput(
            current_annual_shipped_milk_kg=current_annual_shipped_milk_kg,
            future_annual_shipped_milk_kg=future_annual_shipped_milk_kg,
            milk_price_yen_per_kg=financial_assumptions.milk_price_yen_per_kg,
        )
    )
    financial_comparison = _financial_comparison(
        navigation.plans,
        financial_assumptions,
        input_source_kinds,
        covered_cow_overrides,
    )
    climate_background = _climate_background(
        navigation.plans,
        financial_assumptions,
        covered_cow_overrides,
    )
    return {
        "navigation": navigation,
        "path_comparison": path_comparison,
        "financial_comparison": financial_comparison,
        "climate_background": climate_background,
        "annual_heat_path_comparison": _annual_heat_path_comparison_view(
            plans=navigation.plans,
            initial_uncovered_cow_count=(
                two_horizon_screening.current_before.estimated_uncovered_cow_count
            ),
            assumptions=financial_assumptions,
            climate_background=climate_background,
            covered_cow_overrides=covered_cow_overrides,
        ),
        "two_horizon_financial": _two_horizon_financial_view(
            first_phase_plan=navigation.plans[1],
            covered_cow_count=(
                two_horizon_screening.covered_cow_count_for_finance
            ),
            assumptions=financial_assumptions,
            climate_background=climate_background,
            future_target_cow_count=future_target_cow_count,
        ),
        "operating_hours": {
            "value": float(effective_operating_hours),
            "value_ja": _format_decimal(effective_operating_hours),
            "source_kind": operating_hours_source_kind,
            "is_user_input": hours_were_entered,
        },
        "financial_inputs": {
            "avoided_milk_loss_kg_per_cow_day": {
                "value": float(
                    financial_assumptions.avoided_milk_loss_kg_per_cow_day
                    or Decimal("0")
                ),
                "value_ja": _format_decimal(
                    financial_assumptions.avoided_milk_loss_kg_per_cow_day
                    or Decimal("0")
                ),
                "source_kind": input_source_kinds[
                    "avoided_milk_loss_kg_per_cow_day"
                ],
                "is_user_input": avoided_milk_loss_kg_per_cow_day is not None,
            },
            "milk_price_yen_per_kg": {
                "value": float(financial_assumptions.milk_price_yen_per_kg),
                "value_ja": _format_decimal(
                    financial_assumptions.milk_price_yen_per_kg
                ),
                "source_kind": input_source_kinds["milk_price_yen_per_kg"],
                "is_user_input": milk_price_yen_per_kg is not None,
            },
            "electricity_price_yen_per_kwh": {
                "value": float(
                    financial_assumptions.electricity_price_yen_per_kwh
                ),
                "value_ja": _format_decimal(
                    financial_assumptions.electricity_price_yen_per_kwh
                ),
                "source_kind": input_source_kinds[
                    "electricity_price_yen_per_kwh"
                ],
                "is_user_input": electricity_price_yen_per_kwh is not None,
            },
        },
        "farm_sales_context": {
            "is_available": (
                current_annual_shipped_milk_kg is not None
                or future_annual_shipped_milk_kg is not None
            ),
            "current_annual_shipped_milk_kg": (
                float(current_annual_shipped_milk_kg)
                if current_annual_shipped_milk_kg is not None
                else None
            ),
            "current_annual_shipped_milk_ja": _format_annual_kg(
                current_annual_shipped_milk_kg
            ),
            "current_annual_milk_sales_ja": (
                _format_yen(farm_sales_context.current_annual_milk_sales_yen)
                if farm_sales_context.current_annual_milk_sales_yen is not None
                else "未評価"
            ),
            "future_annual_shipped_milk_kg": (
                float(future_annual_shipped_milk_kg)
                if future_annual_shipped_milk_kg is not None
                else None
            ),
            "future_annual_shipped_milk_ja": _format_annual_kg(
                future_annual_shipped_milk_kg
            ),
            "future_annual_milk_sales_ja": (
                _format_yen(farm_sales_context.future_annual_milk_sales_yen)
                if farm_sales_context.future_annual_milk_sales_yen is not None
                else "未評価"
            ),
        },
        "two_horizon_screening": two_horizon_screening,
        "equipment_branches": _equipment_branch_views(
            standard_fan_count=navigation.plans[1].additional_fan_count,
            standard_covered_cow_count=(
                two_horizon_screening.covered_cow_count_for_finance
            ),
            assumptions=financial_assumptions,
            standard_coverage_confirmed=(
                confirmed_covered_cow_count is not None
            ),
        ),
        "viewer_payload": asdict(navigation) | {
            "selected_plan": "first_phase",
            "path_comparison": asdict(path_comparison),
            "two_horizon_screening": {
                "current_before": asdict(two_horizon_screening.current_before),
                "current_after": asdict(two_horizon_screening.current_after),
                "future_after": (
                    asdict(two_horizon_screening.future_after)
                    if two_horizon_screening.future_after is not None
                    else None
                ),
                "transition_has_guideline_gap": (
                    two_horizon_screening.transition_has_guideline_gap
                ),
            },
            "input_mode": "guideline_reference" if reference_mode else "confirmed",
        },
        "evidence": _evidence(
            inputs,
            navigation.current_state,
            navigation.plans[1].additional_fan_count,
            financial_assumptions,
            input_source_kinds,
            reference_mode=reference_mode,
            future_target_cow_count=future_target_cow_count,
            confirmed_covered_cow_count=confirmed_covered_cow_count,
            current_annual_shipped_milk_kg=current_annual_shipped_milk_kg,
            future_annual_shipped_milk_kg=future_annual_shipped_milk_kg,
        ),
        "input_mode": "guideline_reference" if reference_mode else "confirmed",
    }


def _candidate_view(candidate: NaturalInputCandidate) -> dict[str, Any]:
    region_unsupported = candidate.region_ja not in (None, SUPPORTED_REGION_JA)
    missing_labels = {
        "lactating_cows": "搾乳牛頭数",
        "lane_count": "牛床列数",
        "existing_fan_count": "既存ファン数",
    }
    remaining_missing = tuple(
        field for field in candidate.missing_fields if field != "region_ja"
    )
    can_show_reference = (
        candidate.lactating_cows is not None
        and candidate.lane_count is not None
        and candidate.existing_fan_count is None
    )
    return {
        "region_ja": SUPPORTED_REGION_JA,
        "region_note": (
            f"入力された地域は現在未対応のため、{SUPPORTED_REGION_JA}を使用"
            if region_unsupported
            else "現在の対応地域として設定（千葉市のみ）"
        ),
        "lactating_cows": candidate.lactating_cows,
        "lane_count": candidate.lane_count,
        "existing_fan_count": candidate.existing_fan_count,
        "future_target_cow_count": candidate.future_target_cow_count,
        "missing_fields": remaining_missing,
        "missing_labels": tuple(missing_labels[field] for field in remaining_missing),
        "reference_fan_count": (
            guideline_fan_count(candidate.lactating_cows)
            if can_show_reference and candidate.lactating_cows is not None
            else None
        ),
    }


@app.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    """Explain the product boundary before asking for farm conditions."""

    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"dashboard": _dashboard(60, 2, 10, None, 2026)},
    )


@app.get("/check", response_class=HTMLResponse)
def check(
    request: Request,
    lactating_cows: int = Query(60, ge=1, le=300),
    lane_count: int = Query(2),
    existing_fan_count: int = Query(10, ge=0),
    first_phase_fan_count: int | None = Query(None, ge=0),
    investment_year: int = Query(2026, ge=2026, le=2030),
    planned_fan_count: str | None = Query(None),
    operating_hours_per_day: str | None = Query(None),
    region_ja: str = Query(SUPPORTED_REGION_JA),
    reference_mode: bool = Query(False),
    future_target_cow_count: str | None = Query(None),
    confirmed_covered_cow_count: str | None = Query(None),
    avoided_milk_loss_kg_per_cow_day: str | None = Query(None),
    milk_price_yen_per_kg: str | None = Query(None),
    electricity_price_yen_per_kwh: str | None = Query(None),
    current_annual_shipped_milk_kg: str | None = Query(None),
    future_annual_shipped_milk_kg: str | None = Query(None),
) -> HTMLResponse:
    try:
        region_ja = SUPPORTED_REGION_JA
        parsed_planned_fan_count = _optional_int(planned_fan_count, "今回の計画総台数")
        parsed_operating_hours = _optional_operating_hours(operating_hours_per_day)
        parsed_avoided_milk = _optional_non_negative_decimal(
            avoided_milk_loss_kg_per_cow_day, "夏季の防止乳量差"
        )
        parsed_milk_price = _optional_non_negative_decimal(
            milk_price_yen_per_kg, "実現乳価"
        )
        parsed_electricity_price = _optional_non_negative_decimal(
            electricity_price_yen_per_kwh, "電力量単価"
        )
        parsed_current_shipment = _optional_non_negative_decimal(
            current_annual_shipped_milk_kg, "現在の年間出荷乳量"
        )
        parsed_future_shipment = _optional_non_negative_decimal(
            future_annual_shipped_milk_kg, "5年後の年間出荷乳量"
        )
        parsed_future_target = _optional_bounded_int(
            future_target_cow_count,
            "5年後の対策対象頭数",
            minimum=1,
            maximum=300,
        )
        parsed_confirmed_coverage = _optional_bounded_int(
            confirmed_covered_cow_count,
            "牛体付近2m/s以上を確認できた対象頭数",
            minimum=0,
            maximum=300,
        )
        dashboard = _dashboard(
            lactating_cows,
            lane_count,
            existing_fan_count,
            first_phase_fan_count,
            investment_year,
            parsed_planned_fan_count,
            region_ja,
            reference_mode,
            parsed_operating_hours,
            parsed_future_target,
            parsed_confirmed_coverage,
            parsed_avoided_milk,
            parsed_milk_price,
            parsed_electricity_price,
            parsed_current_shipment,
            parsed_future_shipment,
        )
        error = None
    except (
        AdaptationInputError,
        FarmSalesContextInputError,
        InputValidationError,
    ) as exc:
        dashboard = _dashboard(60, 2, 10, None, 2026, None)
        error = str(exc)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "dashboard": dashboard,
            "error": error,
            "candidate": None,
            "natural_input_error": None,
            "farm_description": "",
        },
    )


@app.post("/explain", response_class=HTMLResponse)
def explain_screening_result(
    request: Request,
    lactating_cows: int = Form(...),
    lane_count: int = Form(...),
    existing_fan_count: int = Form(...),
    first_phase_fan_count: int | None = Form(None),
    investment_year: int = Form(...),
    planned_fan_count: str | None = Form(None),
    operating_hours_per_day: str | None = Form(None),
    region_ja: str = Form(SUPPORTED_REGION_JA),
    reference_mode: bool = Form(False),
    future_target_cow_count: str | None = Form(None),
    confirmed_covered_cow_count: str | None = Form(None),
    avoided_milk_loss_kg_per_cow_day: str | None = Form(None),
    milk_price_yen_per_kg: str | None = Form(None),
    electricity_price_yen_per_kwh: str | None = Form(None),
    current_annual_shipped_milk_kg: str | None = Form(None),
    future_annual_shipped_milk_kg: str | None = Form(None),
    explainer: OpenAIResultExplainer = Depends(get_result_explainer),
) -> HTMLResponse:
    region_ja = SUPPORTED_REGION_JA
    parsed_planned_fan_count = _optional_int(
        planned_fan_count, "今回の計画総台数"
    )
    parsed_operating_hours = _optional_operating_hours(operating_hours_per_day)
    parsed_avoided_milk = _optional_non_negative_decimal(
        avoided_milk_loss_kg_per_cow_day, "夏季の防止乳量差"
    )
    parsed_milk_price = _optional_non_negative_decimal(
        milk_price_yen_per_kg, "実現乳価"
    )
    parsed_electricity_price = _optional_non_negative_decimal(
        electricity_price_yen_per_kwh, "電力量単価"
    )
    parsed_current_shipment = _optional_non_negative_decimal(
        current_annual_shipped_milk_kg, "現在の年間出荷乳量"
    )
    parsed_future_shipment = _optional_non_negative_decimal(
        future_annual_shipped_milk_kg, "5年後の年間出荷乳量"
    )
    parsed_future_target = _optional_bounded_int(
        future_target_cow_count,
        "5年後の対策対象頭数",
        minimum=1,
        maximum=300,
    )
    parsed_confirmed_coverage = _optional_bounded_int(
        confirmed_covered_cow_count,
        "牛体付近2m/s以上を確認できた対象頭数",
        minimum=0,
        maximum=300,
    )
    dashboard = _dashboard(
        lactating_cows,
        lane_count,
        existing_fan_count,
        first_phase_fan_count,
        investment_year,
        parsed_planned_fan_count,
        region_ja,
        reference_mode,
        parsed_operating_hours,
        parsed_future_target,
        parsed_confirmed_coverage,
        parsed_avoided_milk,
        parsed_milk_price,
        parsed_electricity_price,
        parsed_current_shipment,
        parsed_future_shipment,
    )
    payload = _result_explanation_payload(dashboard)
    api_failed = False
    try:
        explanation = explainer.explain(payload)
    except ResultExplanationUnavailable:
        explanation = build_fallback_explanation(
            reference_mode,
            dashboard["two_horizon_screening"].next_check_key,
        )
        api_failed = True
    dashboard["result_explanation"] = asdict(explanation) | {
        "facts_ja": _result_facts_ja(payload),
        "api_failed": api_failed,
    }
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "dashboard": dashboard,
            "error": None,
            "candidate": None,
            "natural_input_error": None,
            "farm_description": "",
        },
    )


@app.post("/interpret", response_class=HTMLResponse)
def interpret_farm_description(
    request: Request,
    farm_description: str = Form(...),
    interpreter: OpenAINaturalInputInterpreter = Depends(get_natural_input_interpreter),
) -> HTMLResponse:
    dashboard = _dashboard(60, 2, 10, None, 2026)
    candidate: NaturalInputCandidate | None = None
    natural_input_error: str | None = None
    try:
        candidate = interpreter.interpret(farm_description)
    except NaturalInputUnavailable:
        natural_input_error = "自然文の読み取りを利用できませんでした。下の4項目を手入力してください。"
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "dashboard": dashboard,
            "error": None,
            "candidate": _candidate_view(candidate) if candidate is not None else None,
            "natural_input_error": natural_input_error,
            "farm_description": farm_description,
        },
    )

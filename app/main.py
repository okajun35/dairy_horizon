"""FastAPI entry point for the Dairy Horizon adaptation navigator."""

from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal, ROUND_HALF_UP
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.climate_profile import (
    ClimatePeriodSummary,
    calculate_operating_hours,
    load_climate_profile,
    summarize_thi_days,
)
from app.financial_screening import (
    FinancialPlan,
    STANDARD_FINANCIAL_ASSUMPTIONS,
    STANDARD_USEFUL_LIFE_YEARS,
    calculate_financial_screening,
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
from app.result_explanation import (
    OpenAIResultExplainer,
    ResultExplanationUnavailable,
    build_fallback_explanation,
)


ROOT = Path(__file__).resolve().parents[1]
CLIMATE_PROFILE_PATH = (
    ROOT / "data/climate_profiles/generated/chiba_city_2025_2034.json"
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


def _format_yen(value: Decimal | None) -> str:
    if value is None:
        return "評価対象外"
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}円"


def _format_milk_kg_per_cow_day(value: Decimal | None) -> str:
    if value is None:
        return "評価対象外"
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:.2f}kg／頭・日"


def _rounded_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _climate_plan_view(
    plan: FanPlan,
    summary: ClimatePeriodSummary,
) -> dict[str, Any]:
    financial_plan = FinancialPlan(
        additional_fan_count=plan.additional_fan_count,
        newly_covered_cow_count=len(plan.newly_covered_cow_ids),
    )
    results = {
        key: calculate_financial_screening(
            financial_plan,
            replace(STANDARD_FINANCIAL_ASSUMPTIONS, heat_days_per_year=days),
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
        "newly_covered_cow_count": len(plan.newly_covered_cow_ids),
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
    summary: ClimatePeriodSummary,
    plans: tuple[FanPlan, ...],
) -> dict[str, Any]:
    operating_hours = calculate_operating_hours(
        summary, STANDARD_FINANCIAL_ASSUMPTIONS.operating_hours_per_day
    )
    return {
        "key": f"{summary.start_year}_{summary.end_year}",
        "start_year": summary.start_year,
        "end_year": summary.end_year,
        "model_count": summary.model_count,
        "median_annual_days": float(summary.median_annual_days),
        "minimum_annual_days": float(summary.minimum_annual_days),
        "maximum_annual_days": float(summary.maximum_annual_days),
        "median_annual_days_ja": f"{_rounded_int(summary.median_annual_days)}日／年",
        "annual_days_range_ja": (
            f"{_rounded_int(summary.minimum_annual_days)}"
            f"〜{_rounded_int(summary.maximum_annual_days)}日／年"
        ),
        "median_annual_hours": float(operating_hours.median_annual_hours),
        "minimum_annual_hours": float(operating_hours.minimum_annual_hours),
        "maximum_annual_hours": float(operating_hours.maximum_annual_hours),
        "plans": tuple(_climate_plan_view(plan, summary) for plan in plans[1:]),
    }


def _climate_background(plans: tuple[FanPlan, ...]) -> dict[str, Any]:
    profile = load_climate_profile(CLIMATE_PROFILE_PATH)
    summaries = (
        summarize_thi_days(profile, 2026, 2030),
        summarize_thi_days(profile, 2031, 2034),
    )
    return {
        "available": True,
        "region_name_ja": summaries[0].region_name_ja,
        "thi_threshold": float(summaries[0].thi_threshold),
        "operating_hours_per_day": float(
            STANDARD_FINANCIAL_ASSUMPTIONS.operating_hours_per_day
        ),
        "periods": tuple(_climate_period_view(summary, plans) for summary in summaries),
        "source_provider": summaries[0].source_provider,
        "source_dataset": summaries[0].source_dataset,
    }


def _financial_plan_view(plan: FanPlan) -> dict[str, Any]:
    result = calculate_financial_screening(
        FinancialPlan(
            additional_fan_count=plan.additional_fan_count,
            newly_covered_cow_count=len(plan.newly_covered_cow_ids),
        ),
        STANDARD_FINANCIAL_ASSUMPTIONS,
    )
    if result.status == "not_applicable":
        status_note_ja = "現在の入力では追加投資がないため、回収条件は評価対象外です。"
    elif result.status == "recovery_impossible":
        status_note_ja = "現在の標準条件では回収に必要な乳量を計算できません。"
    else:
        status_note_ja = "標準仮定による粗い比較です。実際の見積額と夏季乳量差で確認します。"
    return {
        "key": plan.key,
        "label_ja": plan.label_ja,
        "additional_fan_count": plan.additional_fan_count,
        "newly_covered_cow_count": len(plan.newly_covered_cow_ids),
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


def _financial_comparison(plans: tuple[FanPlan, ...]) -> dict[str, Any]:
    assumptions = STANDARD_FINANCIAL_ASSUMPTIONS
    return {
        "plans": tuple(_financial_plan_view(plan) for plan in plans[1:]),
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
                "label": "運転期間",
                "value": (
                    f"{assumptions.operating_hours_per_day}時間／日 × "
                    f"{assumptions.heat_days_per_year}日／年"
                ),
                "kind": "industry_guidance",
            },
            {
                "label": "電力量単価",
                "value": f"{assumptions.electricity_price_yen_per_kwh}円／kWh",
                "kind": "industry_guidance",
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
                "label": "乳価",
                "value": f"{assumptions.milk_price_yen_per_kg}円／kg",
                "kind": "industry_guidance",
            },
            {
                "label": "防げる乳量",
                "value": (
                    f"{assumptions.avoided_milk_loss_kg_per_cow_day}kg／頭・日"
                ),
                "kind": "demo_assumption",
            },
        ),
    }


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
    return {
        "input": {
            "region_ja": navigation.inputs.region_ja,
            "lactating_cows": navigation.inputs.lactating_cows,
            "lane_count": navigation.inputs.lane_count,
            "existing_fan_count": navigation.inputs.existing_fan_count,
            "reference_mode": dashboard["input_mode"] == "guideline_reference",
        },
        "current": {
            "guideline_fan_count": current.guideline_fan_count,
            "fan_shortage": current.guideline_gap_fan_count,
            "uncovered_cow_count": len(current.estimated_uncovered_cow_ids),
        },
        "plans": plans,
        "climate": {
            "region_name_ja": climate["region_name_ja"],
            "thi_threshold": climate["thi_threshold"],
            "operating_hours_per_day": climate["operating_hours_per_day"],
            "periods": tuple(
                {
                    "start_year": period["start_year"],
                    "end_year": period["end_year"],
                    "model_count": period["model_count"],
                    "median_annual_days": period["median_annual_days"],
                    "minimum_annual_days": period["minimum_annual_days"],
                    "maximum_annual_days": period["maximum_annual_days"],
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
    near_future = payload["climate"]["periods"][0]
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
        f"{near_future['start_year']}〜{near_future['end_year']}年の暑熱対象日は"
        f"中央値{_rounded_int(Decimal(str(near_future['median_annual_days'])))}日、"
        f"モデル範囲{_rounded_int(Decimal(str(near_future['minimum_annual_days'])))}"
        f"〜{_rounded_int(Decimal(str(near_future['maximum_annual_days'])))}日／年です。",
    )


def _evidence(
    inputs: BarnInput,
    current_state: CurrentBarnState,
    first_phase_fan_count: int,
    *,
    reference_mode: bool = False,
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
    return input_rows + (
        {"item": "ファンのカバー目安", "value": "3頭／台・牛体付近2m/s以上", "kind": current_state.coverage_basis_kind, "source": "全酪連 COW BELL No.178『暑熱対策の設備投資を考える』pp.6-8", "note": "実際の間隔・風量・設置位置で必ず確認します。"},
        {"item": "頭数基準の台数目安", "value": f"{current_state.guideline_fan_count}台", "kind": "industry_guidance", "source": "搾乳牛頭数を3頭／台で割り、全体で切り上げ", "note": "投資試算用の目安です。列数による自動補正は行いません。"},
        {"item": "法定耐用年数", "value": f"{STANDARD_USEFUL_LIFE_YEARS}年", "kind": "industry_guidance", "source": "全酪連 COW BELL No.178の標準計算例", "note": "採算計算の年割りに使います。実際の故障年や交換年ではありません。"},
    ) + comparison_rows + (
        {"item": "将来気候", "value": "2026〜2034年を期間集計して表示", "kind": "processed_cmip6_api", "source": "Open-Meteo Climate API・CMIP6複数モデルの保存済みプロファイル", "note": "日平均THI 72以上の日数をモデル間の中央値と範囲で示します。ファン台数・投資時期には使いません。"},
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
    return {
        "navigation": navigation,
        "path_comparison": path_comparison,
        "financial_comparison": _financial_comparison(navigation.plans),
        "climate_background": _climate_background(navigation.plans),
        "viewer_payload": asdict(navigation) | {
            "selected_plan": "first_phase",
            "path_comparison": asdict(path_comparison),
            "input_mode": "guideline_reference" if reference_mode else "confirmed",
        },
        "evidence": _evidence(
            inputs,
            navigation.current_state,
            navigation.plans[1].additional_fan_count,
            reference_mode=reference_mode,
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
        "missing_fields": remaining_missing,
        "missing_labels": tuple(missing_labels[field] for field in remaining_missing),
        "reference_fan_count": (
            guideline_fan_count(candidate.lactating_cows)
            if can_show_reference and candidate.lactating_cows is not None
            else None
        ),
    }


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    lactating_cows: int = Query(60, ge=1, le=300),
    lane_count: int = Query(2),
    existing_fan_count: int = Query(10, ge=0),
    first_phase_fan_count: int | None = Query(None, ge=0),
    investment_year: int = Query(2026, ge=2026, le=2030),
    planned_fan_count: str | None = Query(None),
    region_ja: str = Query(SUPPORTED_REGION_JA),
    reference_mode: bool = Query(False),
) -> HTMLResponse:
    try:
        region_ja = SUPPORTED_REGION_JA
        parsed_planned_fan_count = _optional_int(planned_fan_count, "今回の計画総台数")
        dashboard = _dashboard(
            lactating_cows,
            lane_count,
            existing_fan_count,
            first_phase_fan_count,
            investment_year,
            parsed_planned_fan_count,
            region_ja,
            reference_mode,
        )
        error = None
    except InputValidationError as exc:
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
    region_ja: str = Form(SUPPORTED_REGION_JA),
    reference_mode: bool = Form(False),
    explainer: OpenAIResultExplainer = Depends(get_result_explainer),
) -> HTMLResponse:
    region_ja = SUPPORTED_REGION_JA
    parsed_planned_fan_count = _optional_int(
        planned_fan_count, "今回の計画総台数"
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
    )
    payload = _result_explanation_payload(dashboard)
    api_failed = False
    try:
        explanation = explainer.explain(payload)
    except ResultExplanationUnavailable:
        explanation = build_fallback_explanation(reference_mode)
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

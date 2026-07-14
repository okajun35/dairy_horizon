"""FastAPI entry point for the Dairy Horizon adaptation navigator."""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.navigator import (
    BarnInput,
    CurrentBarnState,
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


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
app = FastAPI(title="Dairy Horizon")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def get_natural_input_interpreter() -> OpenAINaturalInputInterpreter:
    """Build the API adapter without exposing credentials to route or template code."""
    return OpenAINaturalInputInterpreter(
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
    ) + comparison_rows + (
        {"item": "将来気候", "value": "保存済み・この画面では未接続", "kind": "derived", "source": "CMIP6複数モデルの生成済み気候プロファイル", "note": "接続時も、ファン台数・投資時期の計算には使いません。"},
    )


def _dashboard(
    lactating_cows: int,
    lane_count: int,
    existing_fan_count: int,
    first_phase_fan_count: int | None,
    investment_year: int,
    planned_fan_count: int | None = None,
    region_ja: str = "千葉市",
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
    region_defaulted = candidate.region_ja is None
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
        "region_ja": candidate.region_ja or "千葉市",
        "region_defaulted": region_defaulted,
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
    region_ja: str = Query("千葉市"),
    reference_mode: bool = Query(False),
) -> HTMLResponse:
    try:
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

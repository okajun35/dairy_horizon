"""FastAPI entry point for the Dairy Horizon adaptation navigator."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.navigator import BarnInput, InputValidationError, build_navigation


ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="Dairy Horizon")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def _evidence(inputs: BarnInput) -> tuple[dict[str, str], ...]:
    return (
        {"item": "搾乳牛頭数・牛床列数・既存ファン数", "value": f"{inputs.lactating_cows}頭・{inputs.lane_count}列・{inputs.existing_fan_count}台", "kind": "user_input", "source": "今回の入力", "note": "結果を更新すると反映されます。"},
        {"item": "ファンのカバー目安", "value": "3頭／台", "kind": "demo_assumption", "source": "千葉60頭デモの配置仮定", "note": "実際の間隔・風量・設置位置で必ず確認します。"},
        {"item": "第1期の表示例", "value": "最大5台", "kind": "demo_assumption", "source": "段階導入を比較するための表示仮定", "note": "推奨台数ではありません。見積・設置位置で置き換えます。"},
        {"item": "将来気候", "value": "保存済み・この画面では未接続", "kind": "derived", "source": "CMIP6複数モデルの生成済み気候プロファイル", "note": "接続時も、ファン台数・投資時期の計算には使いません。"},
    )


def _dashboard(lactating_cows: int, lane_count: int, existing_fan_count: int) -> dict[str, Any]:
    inputs = BarnInput(lactating_cows=lactating_cows, lane_count=lane_count, existing_fan_count=existing_fan_count)
    navigation = build_navigation(inputs)
    return {
        "navigation": navigation,
        "viewer_payload": asdict(navigation),
        "evidence": _evidence(inputs),
    }


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    lactating_cows: int = Query(60, ge=1, le=300),
    lane_count: int = Query(2),
    existing_fan_count: int = Query(10, ge=0),
) -> HTMLResponse:
    try:
        dashboard = _dashboard(lactating_cows, lane_count, existing_fan_count)
        error = None
    except InputValidationError as exc:
        dashboard = _dashboard(60, 2, 10)
        error = str(exc)
    return templates.TemplateResponse(request=request, name="index.html", context={"dashboard": dashboard, "error": error})

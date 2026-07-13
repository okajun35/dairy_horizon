from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.vertical_slice import (
    InputValidationError,
    build_screening_dashboard,
    display_money,
    display_number,
    screening_form_values_from_farm,
    load_farm_and_climate,
)


ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="Dairy Horizon")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
templates.env.globals.update(money=display_money, number=display_number)


def render(request: Request, dashboard: dict[str, Any], error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "dashboard": dashboard,
            "error": error,
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return render(request, build_screening_dashboard())


@app.post("/", response_class=HTMLResponse)
def recalculate(
    request: Request,
    lactating_cows: str = Form("60"),
    lane_count: str = Form("2"),
    existing_fan_count: str = Form("10"),
    milk_price_yen_per_kg: str = Form("135"),
    target_years: str = Form("5"),
    detail_mode: str = Form("false"),
    variable_cost_ratio_pct: str = Form("60"),
    avoided_milk_loss_kg_per_cow_day: str = Form("3"),
    electricity_price_yen_per_kwh: str = Form("27"),
    installed_cost_yen_per_unit: str = Form("220000"),
    consumption_tax_rate_pct: str = Form("10"),
    tax_basis: str = Form("tax_exclusive"),
    annual_interest_rate_pct: str = Form("0"),
    capital_repayment_years: str = Form("7"),
    evaluation_period_years: str = Form("5"),
    climate_year: str = Form("2030"),
    stage_one_year: str = Form(""),
    full_installation_year: str = Form(""),
    milk_price_change_yen_per_kg_per_year: str = Form("0"),
    electricity_price_change_pct_per_year: str = Form("0"),
    annual_cash_before_heat_yen: str = Form("1600000"),
    starting_cash_reserve_yen: str = Form("1000000"),
    maximum_debt_yen: str = Form("2500000"),
    minimum_annual_cash_yen: str = Form("0"),
    existing_fans_service_until_year: str = Form("2032"),
    maximum_uncovered_cow_heat_days: str = Form("3200"),
    selected_plan: str = Form("full_installation"),
) -> HTMLResponse:
    submitted = {
        "lactating_cows": lactating_cows,
        "lane_count": lane_count,
        "existing_fan_count": existing_fan_count,
        "milk_price_yen_per_kg": milk_price_yen_per_kg,
        "target_years": target_years,
        "detail_mode": detail_mode,
        "variable_cost_ratio_pct": variable_cost_ratio_pct,
        "avoided_milk_loss_kg_per_cow_day": avoided_milk_loss_kg_per_cow_day,
        "electricity_price_yen_per_kwh": electricity_price_yen_per_kwh,
        "installed_cost_yen_per_unit": installed_cost_yen_per_unit,
        "consumption_tax_rate_pct": consumption_tax_rate_pct,
        "tax_basis": tax_basis,
        "annual_interest_rate_pct": annual_interest_rate_pct,
        "capital_repayment_years": capital_repayment_years,
        "evaluation_period_years": evaluation_period_years,
        "climate_year": climate_year,
        "stage_one_year": stage_one_year,
        "full_installation_year": full_installation_year,
        "milk_price_change_yen_per_kg_per_year": milk_price_change_yen_per_kg_per_year,
        "electricity_price_change_pct_per_year": electricity_price_change_pct_per_year,
        "annual_cash_before_heat_yen": annual_cash_before_heat_yen,
        "starting_cash_reserve_yen": starting_cash_reserve_yen,
        "maximum_debt_yen": maximum_debt_yen,
        "minimum_annual_cash_yen": minimum_annual_cash_yen,
        "existing_fans_service_until_year": existing_fans_service_until_year,
        "maximum_uncovered_cow_heat_days": maximum_uncovered_cow_heat_days,
        "selected_plan": selected_plan,
    }
    try:
        return render(request, build_screening_dashboard(submitted))
    except (InputValidationError, ValueError) as exc:
        farm, _ = load_farm_and_climate()
        dashboard = build_screening_dashboard()
        dashboard["values"] = screening_form_values_from_farm(farm) | submitted
        return render(request, dashboard, str(exc))

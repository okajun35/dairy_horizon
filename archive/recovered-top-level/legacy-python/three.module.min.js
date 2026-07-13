from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


AnnualisationMethod = Literal[
    "straight_line",
    "capital_recovery_factor",
]


@dataclass(frozen=True)
class ZenrakurenInputs:
    fan_body_yen_per_unit: float
    inverter_yen_per_unit: float
    installation_yen_per_unit: float
    rated_power_kw: float
    energy_charge_yen_per_kwh: float
    basic_charge_yen_per_kw_month: float
    hours_per_day: float
    active_days: int
    inverter_reduction_ratio_pct: float
    useful_life_years: int
    annual_interest_rate_pct: float
    annualisation_method: AnnualisationMethod
    variable_cost_ratio_pct: float
    milk_price_yen_per_kg: float
    cows_covered_per_fan: int
    tax_basis: str
    consumption_tax_rate_pct: float

    def validate(self) -> None:
        non_negative = {
            "fan_body_yen_per_unit": self.fan_body_yen_per_unit,
            "inverter_yen_per_unit": self.inverter_yen_per_unit,
            "installation_yen_per_unit": (
                self.installation_yen_per_unit
            ),
            "rated_power_kw": self.rated_power_kw,
            "energy_charge_yen_per_kwh": (
                self.energy_charge_yen_per_kwh
            ),
            "basic_charge_yen_per_kw_month": (
                self.basic_charge_yen_per_kw_month
            ),
            "hours_per_day": self.hours_per_day,
            "milk_price_yen_per_kg": self.milk_price_yen_per_kg,
        }
        for name, value in non_negative.items():
            if value < 0:
                raise ValueError(f"{name} must be non-negative")

        if self.active_days < 1:
            raise ValueError("active_days must be positive")
        if self.useful_life_years < 1:
            raise ValueError("useful_life_years must be positive")
        if self.cows_covered_per_fan < 1:
            raise ValueError("cows_covered_per_fan must be positive")
        if not 0 <= self.variable_cost_ratio_pct < 100:
            raise ValueError(
                "variable_cost_ratio_pct must be in [0, 100)"
            )
        if not 0 <= self.inverter_reduction_ratio_pct <= 100:
            raise ValueError(
                "inverter_reduction_ratio_pct must be in [0, 100]"
            )


def capital_recovery_factor(
    annual_rate: float,
    years: int,
) -> float:
    if annual_rate == 0:
        return 1.0 / years
    numerator = annual_rate * (1.0 + annual_rate) ** years
    denominator = (1.0 + annual_rate) ** years - 1.0
    return numerator / denominator


def calculate(inputs: ZenrakurenInputs) -> dict[str, Any]:
    inputs.validate()

    capex_per_fan = (
        inputs.fan_body_yen_per_unit
        + inputs.inverter_yen_per_unit
        + inputs.installation_yen_per_unit
    )
    capex_per_cow = capex_per_fan / inputs.cows_covered_per_fan

    if inputs.annualisation_method == "straight_line":
        annualisation_factor = 1.0 / inputs.useful_life_years
    else:
        annualisation_factor = capital_recovery_factor(
            inputs.annual_interest_rate_pct / 100.0,
            inputs.useful_life_years,
        )

    annualised_capex_per_cow = capex_per_cow * annualisation_factor

    annual_basic_per_fan = (
        inputs.basic_charge_yen_per_kw_month
        * inputs.rated_power_kw
        * 12
    )
    annual_energy_per_fan = (
        inputs.energy_charge_yen_per_kwh
        * inputs.rated_power_kw
        * inputs.hours_per_day
        * inputs.active_days
        * (
            1.0
            - inputs.inverter_reduction_ratio_pct / 100.0
        )
    )
    annual_operation_per_cow = (
        annual_basic_per_fan + annual_energy_per_fan
    ) / inputs.cows_covered_per_fan

    annual_burden_per_cow = (
        annualised_capex_per_cow + annual_operation_per_cow
    )
    contribution_margin_ratio = (
        1.0 - inputs.variable_cost_ratio_pct / 100.0
    )
    break_even_sales_per_cow = (
        annual_burden_per_cow / contribution_margin_ratio
    )

    if inputs.milk_price_yen_per_kg == 0:
        break_even_milk_per_cow_year = None
        break_even_milk_per_cow_day = None
        status = "recovery_impossible_at_zero_price"
    else:
        break_even_milk_per_cow_year = (
            break_even_sales_per_cow
            / inputs.milk_price_yen_per_kg
        )
        break_even_milk_per_cow_day = (
            break_even_milk_per_cow_year / inputs.active_days
        )
        status = "calculated"

    return {
        "status": status,
        "inputs": asdict(inputs),
        "tax_handling": {
            "tax_basis": inputs.tax_basis,
            "consumption_tax_rate_pct": (
                inputs.consumption_tax_rate_pct
            ),
            "applied_automatically": False,
            "note": (
                "All source amounts must use the same tax basis. "
                "The engine does not apply a blanket tax conversion."
            ),
        },
        "result": {
            "capex_per_fan_yen": round(capex_per_fan, 2),
            "capex_per_cow_yen": round(capex_per_cow, 2),
            "annualisation_factor": round(
                annualisation_factor, 8
            ),
            "annualised_capex_per_cow_yen": round(
                annualised_capex_per_cow, 2
            ),
            "annual_basic_per_fan_yen": round(
                annual_basic_per_fan, 2
            ),
            "annual_energy_per_fan_yen": round(
                annual_energy_per_fan, 2
            ),
            "annual_operation_per_cow_yen": round(
                annual_operation_per_cow, 2
            ),
            "annual_burden_per_cow_yen": round(
                annual_burden_per_cow, 2
            ),
            "break_even_sales_per_cow_yen": round(
                break_even_sales_per_cow, 2
            ),
            "break_even_milk_kg_per_cow_year": (
                None
                if break_even_milk_per_cow_year is None
                else round(break_even_milk_per_cow_year, 4)
            ),
            "break_even_milk_kg_per_cow_day": (
                None
                if break_even_milk_per_cow_day is None
                else round(break_even_milk_per_cow_day, 4)
            ),
        },
    }


def effective_milk_price(
    *,
    base_price_yen_per_kg: float,
    change_yen_per_kg: float,
) -> float:
    return max(0.0, base_price_yen_per_kg + change_yen_per_kg)


def inputs_from_scenario(payload: dict[str, Any]) -> ZenrakurenInputs:
    values = payload["financial_input"]
    milk_price = effective_milk_price(
        base_price_yen_per_kg=float(
            values["base_milk_price_yen_per_kg"]
        ),
        change_yen_per_kg=float(
            values["milk_price_change_yen_per_kg"]
        ),
    )
    return ZenrakurenInputs(
        fan_body_yen_per_unit=float(
            values["fan_body_yen_per_unit"]
        ),
        inverter_yen_per_unit=float(
            values["inverter_yen_per_unit"]
        ),
        installation_yen_per_unit=float(
            values["installation_yen_per_unit"]
        ),
        rated_power_kw=float(values["rated_power_kw"]),
        energy_charge_yen_per_kwh=float(
            values["energy_charge_yen_per_kwh"]
        ),
        basic_charge_yen_per_kw_month=float(
            values["basic_charge_yen_per_kw_month"]
        ),
        hours_per_day=float(values["hours_per_day"]),
        active_days=int(values["active_days"]),
        inverter_reduction_ratio_pct=float(
            values["inverter_reduction_ratio_pct"]
        ),
        useful_life_years=int(values["useful_life_years"]),
        annual_interest_rate_pct=float(
            values["annual_interest_rate_pct"]
        ),
        annualisation_method=values["annualisation_method"],
        variable_cost_ratio_pct=float(
            values["variable_cost_ratio_pct"]
        ),
        milk_price_yen_per_kg=milk_price,
        cows_covered_per_fan=int(
            values["cows_covered_per_fan"]
        ),
        tax_basis=values["tax_basis"],
        consumption_tax_rate_pct=float(
            values["consumption_tax_rate_pct"]
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    payload = json.loads(
        args.scenario.read_text(encoding="utf-8")
    )
    result = calculate(inputs_from_scenario(payload))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

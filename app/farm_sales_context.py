"""Farm milk-sales scale shown separately from project economics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class FarmSalesContextInputError(ValueError):
    """Raised when a direct annual milk-sales input is invalid."""


@dataclass(frozen=True)
class FarmSalesContextInput:
    current_annual_shipped_milk_kg: Decimal | None
    future_annual_shipped_milk_kg: Decimal | None
    milk_price_yen_per_kg: Decimal


@dataclass(frozen=True)
class FarmSalesContextResult:
    current_annual_milk_sales_yen: Decimal | None
    future_annual_milk_sales_yen: Decimal | None


def _validate_non_negative(value: Decimal | None, label_ja: str) -> None:
    if value is None:
        return
    if not value.is_finite() or value < 0:
        raise FarmSalesContextInputError(
            f"{label_ja}は0以上の有限値で入力してください。"
        )


def calculate_farm_sales_context(
    inputs: FarmSalesContextInput,
) -> FarmSalesContextResult:
    """Calculate sales scale only from directly supplied annual shipments.

    This function deliberately does not infer shipments from cow count,
    lactation length, or calendar days. Its result is contextual and is not an
    input to the heat-countermeasure project economics.
    """

    _validate_non_negative(
        inputs.current_annual_shipped_milk_kg,
        "現在の年間出荷乳量",
    )
    _validate_non_negative(
        inputs.future_annual_shipped_milk_kg,
        "5年後の年間出荷乳量",
    )
    _validate_non_negative(inputs.milk_price_yen_per_kg, "実現乳価")

    return FarmSalesContextResult(
        current_annual_milk_sales_yen=(
            inputs.current_annual_shipped_milk_kg * inputs.milk_price_yen_per_kg
            if inputs.current_annual_shipped_milk_kg is not None
            else None
        ),
        future_annual_milk_sales_yen=(
            inputs.future_annual_shipped_milk_kg * inputs.milk_price_yen_per_kg
            if inputs.future_annual_shipped_milk_kg is not None
            else None
        ),
    )

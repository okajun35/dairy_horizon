from __future__ import annotations

from decimal import Decimal
import unittest

from app.farm_sales_context import (
    FarmSalesContextInput,
    FarmSalesContextInputError,
    calculate_farm_sales_context,
)


class FarmSalesContextTest(unittest.TestCase):
    def test_uses_direct_annual_shipments_without_lactation_inference(self) -> None:
        result = calculate_farm_sales_context(
            FarmSalesContextInput(
                current_annual_shipped_milk_kg=Decimal("600000"),
                future_annual_shipped_milk_kg=Decimal("450000"),
                milk_price_yen_per_kg=Decimal("150"),
            )
        )

        self.assertEqual(result.current_annual_milk_sales_yen, Decimal("90000000"))
        self.assertEqual(result.future_annual_milk_sales_yen, Decimal("67500000"))

    def test_missing_future_shipment_remains_unevaluated(self) -> None:
        result = calculate_farm_sales_context(
            FarmSalesContextInput(
                current_annual_shipped_milk_kg=Decimal("600000"),
                future_annual_shipped_milk_kg=None,
                milk_price_yen_per_kg=Decimal("150"),
            )
        )

        self.assertEqual(result.current_annual_milk_sales_yen, Decimal("90000000"))
        self.assertIsNone(result.future_annual_milk_sales_yen)

    def test_rejects_negative_shipments(self) -> None:
        with self.assertRaises(FarmSalesContextInputError):
            calculate_farm_sales_context(
                FarmSalesContextInput(
                    current_annual_shipped_milk_kg=Decimal("-1"),
                    future_annual_shipped_milk_kg=None,
                    milk_price_yen_per_kg=Decimal("150"),
                )
            )


if __name__ == "__main__":
    unittest.main()

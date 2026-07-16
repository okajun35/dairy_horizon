from __future__ import annotations

from decimal import Decimal
import unittest

from app.equipment_branches import build_equipment_branches
from app.financial_screening import STANDARD_FINANCIAL_ASSUMPTIONS


class EquipmentBranchTest(unittest.TestCase):
    def test_standard_is_complete_while_other_types_stop_at_electricity(self) -> None:
        branches = build_equipment_branches(
            standard_fan_count=5,
            standard_covered_cow_count=15,
            assumptions=STANDARD_FINANCIAL_ASSUMPTIONS,
        )
        standard, efficient, large = branches

        self.assertEqual(standard.key, "standard_100")
        self.assertEqual(standard.coverage_status, "guidance_estimate")
        self.assertEqual(standard.incremental_capex_yen, Decimal("1100000"))
        self.assertIsNotNone(standard.break_even_milk_kg_per_cow_day)

        self.assertEqual(efficient.key, "efficient_100")
        self.assertEqual(efficient.planned_fan_count, 5)
        self.assertEqual(efficient.annual_electricity_yen, Decimal("92400.00000"))
        self.assertEqual(efficient.coverage_status, "needs_measurement")
        self.assertIsNone(efficient.incremental_capex_yen)
        self.assertIsNone(efficient.break_even_milk_kg_per_cow_day)

        self.assertEqual(large.key, "large_high_airflow")
        self.assertEqual(large.planned_fan_count, 2)
        self.assertEqual(large.annual_electricity_yen, Decimal("155971.200000"))
        self.assertEqual(large.coverage_status, "needs_measurement")
        self.assertIsNone(large.break_even_milk_kg_per_cow_day)

    def test_confirmed_standard_coverage_is_preserved_as_measurement(self) -> None:
        standard = build_equipment_branches(
            standard_fan_count=5,
            standard_covered_cow_count=12,
            assumptions=STANDARD_FINANCIAL_ASSUMPTIONS,
            standard_coverage_confirmed=True,
        )[0]

        self.assertEqual(standard.coverage_status, "confirmed_measurement")
        self.assertEqual(standard.covered_cow_count, 12)
        self.assertGreater(
            standard.break_even_milk_kg_per_cow_day or Decimal("0"),
            Decimal("3.13"),
        )

    def test_no_first_phase_does_not_leave_a_large_fan_demo_investment(self) -> None:
        branches = build_equipment_branches(
            standard_fan_count=0,
            standard_covered_cow_count=0,
            assumptions=STANDARD_FINANCIAL_ASSUMPTIONS,
        )

        self.assertTrue(all(branch.planned_fan_count == 0 for branch in branches))
        self.assertTrue(all(branch.annual_electricity_yen == 0 for branch in branches))


if __name__ == "__main__":
    unittest.main()

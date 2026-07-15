from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import unittest

from app.climate_adjustment import (
    ClimateAdjustmentError,
    anchor_future_thi_days,
    load_observed_thi_baseline,
)
from app.climate_profile import (
    ClimatePeriodSummary,
    load_climate_profile,
    summarize_thi_days,
)


ROOT = Path(__file__).resolve().parents[1]
OBSERVED_PATH = ROOT / "data/observed/jma_chiba_thi_summary_2020_2025.json"
BASELINE_PROFILE_PATH = (
    ROOT / "data/climate_profiles/generated/chiba_city_2020_2025.json"
)
FUTURE_PROFILE_PATH = (
    ROOT / "data/climate_profiles/generated/chiba_city_2025_2034.json"
)


def _summary(
    start_year: int,
    end_year: int,
    values: dict[str, str],
    *,
    threshold: str = "72",
) -> ClimatePeriodSummary:
    days = {name: Decimal(value) for name, value in values.items()}
    ordered = sorted(days.values())
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / Decimal("2")
    )
    return ClimatePeriodSummary(
        region_name_ja="千葉市",
        start_year=start_year,
        end_year=end_year,
        thi_threshold=Decimal(threshold),
        model_count=len(days),
        median_annual_days=median,
        minimum_annual_days=min(ordered),
        maximum_annual_days=max(ordered),
        model_annual_days=days,
        source_provider="test",
        source_dataset="fixture",
    )


class ClimateAdjustmentTest(unittest.TestCase):
    def test_pairs_each_model_before_adding_change_to_observation(self) -> None:
        baseline = _summary(2020, 2025, {"a": "80", "b": "100", "c": "120"})
        future = _summary(2026, 2030, {"a": "90", "b": "115", "c": "110"})

        adjusted = anchor_future_thi_days(
            observed_lower_days=Decimal("97"),
            observed_upper_days=Decimal("98"),
            model_baseline=baseline,
            model_future=future,
        )

        self.assertEqual(
            adjusted.model_change_days,
            {"a": Decimal("10"), "b": Decimal("15"), "c": Decimal("-10")},
        )
        self.assertEqual(adjusted.model_count, 3)
        self.assertEqual(adjusted.median_change_days, Decimal("10"))
        self.assertEqual(adjusted.minimum_change_days, Decimal("-10"))
        self.assertEqual(adjusted.maximum_change_days, Decimal("15"))
        self.assertEqual(adjusted.central_lower_days, Decimal("107"))
        self.assertEqual(adjusted.central_upper_days, Decimal("108"))
        self.assertEqual(
            adjusted.model_adjusted_day_ranges,
            {
                "a": (Decimal("107"), Decimal("108")),
                "b": (Decimal("112"), Decimal("113")),
                "c": (Decimal("87"), Decimal("88")),
            },
        )
        self.assertEqual(adjusted.median_annual_days, Decimal("107.5"))
        self.assertEqual(adjusted.minimum_annual_days, Decimal("87"))
        self.assertEqual(adjusted.maximum_annual_days, Decimal("113"))

    def test_uses_only_models_common_to_baseline_and_future(self) -> None:
        baseline = _summary(2020, 2025, {"a": "80", "b": "100", "old": "50"})
        future = _summary(2026, 2030, {"a": "90", "b": "105", "new": "150"})

        adjusted = anchor_future_thi_days(
            observed_lower_days=Decimal("97"),
            observed_upper_days=Decimal("97.5"),
            model_baseline=baseline,
            model_future=future,
        )

        self.assertEqual(adjusted.model_count, 2)
        self.assertEqual(set(adjusted.model_change_days), {"a", "b"})
        self.assertEqual(adjusted.median_change_days, Decimal("7.5"))

    def test_requires_two_common_models(self) -> None:
        baseline = _summary(2020, 2025, {"a": "80", "old": "100"})
        future = _summary(2026, 2030, {"a": "90", "new": "110"})

        with self.assertRaisesRegex(ClimateAdjustmentError, "共通モデル"):
            anchor_future_thi_days(
                observed_lower_days=Decimal("97"),
                observed_upper_days=Decimal("97.5"),
                model_baseline=baseline,
                model_future=future,
            )

    def test_rejects_different_thi_thresholds(self) -> None:
        baseline = _summary(2020, 2025, {"a": "80", "b": "100"})
        future = _summary(
            2026, 2030, {"a": "90", "b": "105"}, threshold="75"
        )

        with self.assertRaisesRegex(ClimateAdjustmentError, "THI閾値"):
            anchor_future_thi_days(
                observed_lower_days=Decimal("97"),
                observed_upper_days=Decimal("97.5"),
                model_baseline=baseline,
                model_future=future,
            )

    def test_saved_data_produces_six_model_observation_anchored_ranges(self) -> None:
        observed = load_observed_thi_baseline(OBSERVED_PATH)
        model_baseline = summarize_thi_days(
            load_climate_profile(BASELINE_PROFILE_PATH), 2020, 2025
        )
        future_profile = load_climate_profile(FUTURE_PROFILE_PATH)

        near = anchor_future_thi_days(
            observed_lower_days=observed.lower_days,
            observed_upper_days=observed.upper_days,
            model_baseline=model_baseline,
            model_future=summarize_thi_days(future_profile, 2026, 2030),
        )
        later = anchor_future_thi_days(
            observed_lower_days=observed.lower_days,
            observed_upper_days=observed.upper_days,
            model_baseline=model_baseline,
            model_future=summarize_thi_days(future_profile, 2031, 2034),
        )

        self.assertEqual(observed.lower_days, Decimal("97.0"))
        self.assertEqual(observed.upper_days, Decimal("97.5"))
        self.assertEqual(near.model_count, 6)
        self.assertEqual(
            near.median_change_days,
            Decimal("7.31666666666666666666666667"),
        )
        self.assertEqual(
            near.central_lower_days,
            Decimal("104.3166666666666666666666667"),
        )
        self.assertEqual(
            near.minimum_annual_days,
            Decimal("95.53333333333333333333333333"),
        )
        self.assertEqual(
            near.maximum_annual_days,
            Decimal("108.9333333333333333333333333"),
        )
        self.assertEqual(later.model_count, 6)
        self.assertEqual(
            later.median_change_days,
            Decimal("8.083333333333333333333333335"),
        )
        self.assertEqual(
            later.minimum_annual_days,
            Decimal("99.33333333333333333333333333"),
        )
        self.assertEqual(
            later.maximum_annual_days,
            Decimal("109.6666666666666666666666667"),
        )


if __name__ == "__main__":
    unittest.main()

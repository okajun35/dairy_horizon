"""Observation-anchored future THI-day ranges using paired climate models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from statistics import median
from typing import Mapping

from app.climate_profile import ClimatePeriodSummary


class ClimateAdjustmentError(ValueError):
    """Raised when observed and model summaries cannot be compared safely."""


@dataclass(frozen=True)
class ObservedThiBaseline:
    """Annual observed THI-day interval retained across missing values."""

    region_name_ja: str
    start_year: int
    end_year: int
    thi_threshold: Decimal
    lower_days: Decimal
    upper_days: Decimal
    source_publisher: str
    source_dataset: str


@dataclass(frozen=True)
class ObservationAnchoredClimateSummary:
    """Future THI days after adding paired model changes to observations.

    ``central_lower_days`` and ``central_upper_days`` retain the observed
    missing-value interval after adding the median model change. The wider
    minimum/maximum interval includes both that observation interval and the
    spread of paired model changes.
    """

    start_year: int
    end_year: int
    thi_threshold: Decimal
    model_count: int
    observed_lower_days: Decimal
    observed_upper_days: Decimal
    median_change_days: Decimal
    minimum_change_days: Decimal
    maximum_change_days: Decimal
    central_lower_days: Decimal
    central_upper_days: Decimal
    median_annual_days: Decimal
    minimum_annual_days: Decimal
    maximum_annual_days: Decimal
    model_change_days: Mapping[str, Decimal]
    model_adjusted_day_ranges: Mapping[str, tuple[Decimal, Decimal]]


def _decimal(value: object, label_ja: str) -> Decimal:
    if isinstance(value, bool):
        raise ClimateAdjustmentError(f"{label_ja}は数値である必要があります。")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ClimateAdjustmentError(f"{label_ja}は数値である必要があります。") from exc
    if not parsed.is_finite():
        raise ClimateAdjustmentError(f"{label_ja}は有限の数値である必要があります。")
    return parsed


def load_observed_thi_baseline(path: Path) -> ObservedThiBaseline:
    """Load the bounded annual observation summary generated in preprocessing."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        period = payload["period"]
        thi_definition = payload["thi_definition"]
        summary = payload["period_summary"]
        source = payload["source"]
        classification = payload["classification"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ClimateAdjustmentError("観測THI基準データを読み込めません。") from exc
    if classification != "official_observation":
        raise ClimateAdjustmentError("観測THI基準は公式観測データである必要があります。")

    lower = _decimal(summary.get("annual_mean_thi_days_lower_bound"), "観測日数の下限")
    upper = _decimal(summary.get("annual_mean_thi_days_upper_bound"), "観測日数の上限")
    if lower < 0 or upper > 366 or lower > upper:
        raise ClimateAdjustmentError("観測THI対象日数の範囲が正しくありません。")

    try:
        start_year = int(period["start_year"])
        end_year = int(period["end_year"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ClimateAdjustmentError("観測THI基準の期間が正しくありません。") from exc
    region_name = payload.get("region_name_ja")
    if not isinstance(region_name, str) or not region_name:
        raise ClimateAdjustmentError("観測THI基準の地域名がありません。")

    return ObservedThiBaseline(
        region_name_ja=region_name,
        start_year=start_year,
        end_year=end_year,
        thi_threshold=_decimal(thi_definition.get("threshold"), "THI閾値"),
        lower_days=lower,
        upper_days=upper,
        source_publisher=str(source.get("publisher", "")),
        source_dataset=str(source.get("dataset", "")),
    )


def _bounded_day_count(value: Decimal) -> Decimal:
    return min(Decimal("366"), max(Decimal("0"), value))


def anchor_future_thi_days(
    *,
    observed_lower_days: Decimal,
    observed_upper_days: Decimal,
    model_baseline: ClimatePeriodSummary,
    model_future: ClimatePeriodSummary,
) -> ObservationAnchoredClimateSummary:
    """Add each model's future-minus-baseline change to observed THI days."""

    if model_baseline.thi_threshold != model_future.thi_threshold:
        raise ClimateAdjustmentError("比較するデータのTHI閾値が一致しません。")
    if (
        not observed_lower_days.is_finite()
        or not observed_upper_days.is_finite()
        or observed_lower_days < 0
        or observed_upper_days > 366
        or observed_lower_days > observed_upper_days
    ):
        raise ClimateAdjustmentError("観測THI対象日数の範囲が正しくありません。")

    common_models = sorted(
        set(model_baseline.model_annual_days) & set(model_future.model_annual_days)
    )
    if len(common_models) < 2:
        raise ClimateAdjustmentError("比較できる共通モデルが2件以上必要です。")

    changes = {
        model_name: (
            model_future.model_annual_days[model_name]
            - model_baseline.model_annual_days[model_name]
        )
        for model_name in common_models
    }
    change_values = tuple(changes.values())
    adjusted_ranges = {
        model_name: (
            _bounded_day_count(observed_lower_days + change),
            _bounded_day_count(observed_upper_days + change),
        )
        for model_name, change in changes.items()
    }
    median_change = median(change_values)
    central_lower = _bounded_day_count(observed_lower_days + median_change)
    central_upper = _bounded_day_count(observed_upper_days + median_change)
    observed_midpoint = (observed_lower_days + observed_upper_days) / Decimal("2")

    return ObservationAnchoredClimateSummary(
        start_year=model_future.start_year,
        end_year=model_future.end_year,
        thi_threshold=model_future.thi_threshold,
        model_count=len(common_models),
        observed_lower_days=observed_lower_days,
        observed_upper_days=observed_upper_days,
        median_change_days=median_change,
        minimum_change_days=min(change_values),
        maximum_change_days=max(change_values),
        central_lower_days=central_lower,
        central_upper_days=central_upper,
        median_annual_days=_bounded_day_count(observed_midpoint + median_change),
        minimum_annual_days=min(day_range[0] for day_range in adjusted_ranges.values()),
        maximum_annual_days=max(day_range[1] for day_range in adjusted_ranges.values()),
        model_change_days=changes,
        model_adjusted_day_ranges=adjusted_ranges,
    )

"""Deterministic summaries for saved multi-model THI profiles."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping


THI_DAY_FIELD = "thi_days_daily_mean_ge_72"


class ClimateProfileError(ValueError):
    """Raised when a saved profile cannot support the requested summary."""


@dataclass(frozen=True)
class ClimatePeriodSummary:
    """Annual THI-day distribution across models for one bounded period."""

    region_name_ja: str
    start_year: int
    end_year: int
    thi_threshold: Decimal
    model_count: int
    median_annual_days: Decimal
    minimum_annual_days: Decimal
    maximum_annual_days: Decimal
    model_annual_days: Mapping[str, Decimal]
    source_provider: str
    source_dataset: str


@dataclass(frozen=True)
class ClimateOperatingHours:
    """Annual operating-hour distribution using an explicit daily assumption."""

    hours_per_target_day: Decimal
    median_annual_hours: Decimal
    minimum_annual_hours: Decimal
    maximum_annual_hours: Decimal


def load_climate_profile(path: Path) -> Mapping[str, Any]:
    """Load one pre-generated profile without making an external request."""

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClimateProfileError("保存済み気候データを読み込めません。") from exc
    if not isinstance(loaded, dict):
        raise ClimateProfileError("保存済み気候データの形式が正しくありません。")
    return loaded


def _decimal_day_count(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ClimateProfileError("THI対象日数は0〜366日の数値である必要があります。")
    try:
        day_count = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ClimateProfileError(
            "THI対象日数は0〜366日の数値である必要があります。"
        ) from exc
    if not day_count.is_finite() or day_count < 0 or day_count > 366:
        raise ClimateProfileError("THI対象日数は0〜366日の数値である必要があります。")
    return day_count


def summarize_thi_days(
    profile: Mapping[str, Any],
    start_year: int,
    end_year: int,
) -> ClimatePeriodSummary:
    """Summarize mean annual THI days per model, then compare those models.

    The requested period must be fully present in the saved profile. Each
    model's day counts are averaged across the requested years before the
    median and model range are calculated.
    """

    if start_year > end_year:
        raise ClimateProfileError("集計期間の開始年は終了年以前にしてください。")

    period = profile.get("period")
    years = profile.get("years")
    if not isinstance(period, Mapping) or not isinstance(years, Mapping):
        raise ClimateProfileError("保存済み気候データの期間情報が正しくありません。")
    try:
        available_start = int(period["start_year"])
        available_end = int(period["end_year"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ClimateProfileError(
            "保存済み気候データの期間情報が正しくありません。"
        ) from exc
    if start_year < available_start or end_year > available_end:
        raise ClimateProfileError(
            f"{start_year}〜{end_year}年には未取得の気候データが含まれます。"
        )

    requested_years = tuple(range(start_year, end_year + 1))
    model_names_by_year: list[set[str]] = []
    model_values_by_year: dict[int, Mapping[str, Any]] = {}
    for year in requested_years:
        year_data = years.get(str(year))
        if not isinstance(year_data, Mapping):
            raise ClimateProfileError(f"{year}年の気候データは未取得です。")
        model_values = year_data.get("model_values")
        if not isinstance(model_values, Mapping):
            raise ClimateProfileError(f"{year}年のモデル値がありません。")
        model_values_by_year[year] = model_values
        model_names_by_year.append(set(model_values))

    common_models = set.intersection(*model_names_by_year)
    if len(common_models) < 2:
        raise ClimateProfileError(
            "期間全体を比較できる共通モデルが2件以上ありません。"
        )

    year_count = Decimal(len(requested_years))
    annual_days_by_model: dict[str, Decimal] = {}
    for model_name in sorted(common_models):
        total_days = Decimal("0")
        for year in requested_years:
            raw_model = model_values_by_year[year].get(model_name)
            if not isinstance(raw_model, Mapping):
                raise ClimateProfileError(f"{model_name}の{year}年データが不正です。")
            total_days += _decimal_day_count(raw_model.get(THI_DAY_FIELD))
        annual_days_by_model[model_name] = total_days / year_count

    annual_day_values = tuple(annual_days_by_model.values())
    thi_definition = profile.get("thi_definition")
    source = profile.get("source")
    if not isinstance(thi_definition, Mapping) or not isinstance(source, Mapping):
        raise ClimateProfileError("THI定義または出典情報がありません。")

    region_name = profile.get("region_name_ja")
    if not isinstance(region_name, str) or not region_name:
        raise ClimateProfileError("地域名がありません。")

    return ClimatePeriodSummary(
        region_name_ja=region_name,
        start_year=start_year,
        end_year=end_year,
        thi_threshold=_decimal_day_count(thi_definition.get("threshold")),
        model_count=len(annual_day_values),
        median_annual_days=median(annual_day_values),
        minimum_annual_days=min(annual_day_values),
        maximum_annual_days=max(annual_day_values),
        model_annual_days=annual_days_by_model,
        source_provider=str(source.get("provider", "")),
        source_dataset=str(source.get("dataset", "")),
    )


def calculate_operating_hours(
    summary: ClimatePeriodSummary,
    hours_per_target_day: Decimal,
) -> ClimateOperatingHours:
    """Convert THI target days to hours without inferring hourly weather."""

    if (
        not hours_per_target_day.is_finite()
        or not Decimal("0") <= hours_per_target_day <= Decimal("24")
    ):
        raise ClimateProfileError(
            "1対象日あたりの運転時間は0〜24時間で指定してください。"
        )
    return ClimateOperatingHours(
        hours_per_target_day=hours_per_target_day,
        median_annual_hours=summary.median_annual_days * hours_per_target_day,
        minimum_annual_hours=summary.minimum_annual_days * hours_per_target_day,
        maximum_annual_hours=summary.maximum_annual_days * hours_per_target_day,
    )

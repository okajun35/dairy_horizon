"""Pure helpers for validating and summarizing saved weather observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


class ObservedClimateGenerationError(ValueError):
    """Raised when observation rows cannot form an auditable period."""


@dataclass(frozen=True)
class DailyObservation:
    """One daily station observation and its derived daily-mean THI."""

    observed_on: date
    mean_temperature_c: float | None
    mean_relative_humidity_pct: float | None
    thi: float | None
    max_temperature_c: float | None = None
    min_temperature_c: float | None = None
    mean_vapor_pressure_hpa: float | None = None
    min_relative_humidity_pct: float | None = None
    temperature_quality_mark: str = ""
    humidity_quality_mark: str = ""
    source_url: str = ""


@dataclass(frozen=True)
class ObservedPeriodSummary:
    """Completeness and bounded THI-day count for an observation period."""

    start_date: date
    end_date: date
    threshold: float
    expected_days: int
    observed_days: int
    valid_thi_days: int
    missing_observation_dates: tuple[date, ...]
    missing_thi_dates: tuple[date, ...]
    thi_days_lower_bound: int
    thi_days_upper_bound: int

    @property
    def is_complete(self) -> bool:
        return not self.missing_observation_dates and not self.missing_thi_dates


def calculate_daily_mean_thi(
    mean_temperature_c: float,
    mean_relative_humidity_pct: float,
) -> float:
    """Calculate NRC daily-mean screening THI from aligned daily means."""

    if not 0 <= mean_relative_humidity_pct <= 100:
        raise ObservedClimateGenerationError("平均相対湿度は0〜100%で指定してください。")
    humidity_ratio = mean_relative_humidity_pct / 100
    return (
        0.81 * mean_temperature_c
        + humidity_ratio * (0.99 * mean_temperature_c - 14.3)
        + 46.3
    )


def _date_range(start_date: date, end_date: date) -> tuple[date, ...]:
    if start_date > end_date:
        raise ObservedClimateGenerationError("開始日は終了日以前にしてください。")
    day_count = (end_date - start_date).days + 1
    return tuple(start_date + timedelta(days=offset) for offset in range(day_count))


def summarize_observed_period(
    rows: Iterable[DailyObservation],
    *,
    start_date: date,
    end_date: date,
    threshold: float,
) -> ObservedPeriodSummary:
    """Return a bounded count so missing values never silently mean no heat."""

    expected_dates = _date_range(start_date, end_date)
    expected_set = set(expected_dates)
    by_date: dict[date, DailyObservation] = {}
    for row in rows:
        if row.observed_on not in expected_set:
            raise ObservedClimateGenerationError(
                f"集計期間外の日付があります: {row.observed_on.isoformat()}"
            )
        if row.observed_on in by_date:
            raise ObservedClimateGenerationError(
                f"観測日が重複しています: {row.observed_on.isoformat()}"
            )
        by_date[row.observed_on] = row

    missing_observations = tuple(day for day in expected_dates if day not in by_date)
    missing_thi = tuple(
        day for day in expected_dates if day in by_date and by_date[day].thi is None
    )
    valid_values = tuple(
        row.thi for row in by_date.values() if row.thi is not None
    )
    lower_bound = sum(value >= threshold for value in valid_values)
    unknown_days = len(missing_observations) + len(missing_thi)
    return ObservedPeriodSummary(
        start_date=start_date,
        end_date=end_date,
        threshold=threshold,
        expected_days=len(expected_dates),
        observed_days=len(by_date),
        valid_thi_days=len(valid_values),
        missing_observation_dates=missing_observations,
        missing_thi_dates=missing_thi,
        thi_days_lower_bound=lower_bound,
        thi_days_upper_bound=lower_bound + unknown_days,
    )


def period_file_name(prefix: str, start_year: int, end_year: int, suffix: str) -> str:
    """Build an output name from the actual requested period."""

    if start_year > end_year:
        raise ObservedClimateGenerationError("開始年は終了年以前にしてください。")
    normalized_suffix = suffix.removeprefix(".")
    if not prefix or not normalized_suffix:
        raise ObservedClimateGenerationError("出力ファイル名の指定が正しくありません。")
    return f"{prefix}_{start_year}_{end_year}.{normalized_suffix}"

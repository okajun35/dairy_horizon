"""Deterministic assembly of pre-fetched Open-Meteo CMIP6 profiles."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from statistics import median
from typing import Any
from urllib.parse import urlencode

from app.observed_climate_generation import calculate_daily_mean_thi


CLIMATE_API_URL = "https://climate-api.open-meteo.com/v1/climate"
DAILY_VARIABLES = (
    "temperature_2m_mean",
    "temperature_2m_max",
    "relative_humidity_2m_mean",
    "wind_speed_10m_mean",
)
DEFAULT_MODELS = (
    "CMCC_CM2_VHR4",
    "EC_Earth3P_HR",
    "FGOALS_f3_H",
    "HiRAM_SIT_HR",
    "MRI_AGCM3_2_S",
    "MPI_ESM1_2_XR",
    "NICAM16_8S",
)


class ClimateProfileGenerationError(ValueError):
    """Raised when a generated model profile would be incomplete or invalid."""


def _longest_consecutive(values: list[bool]) -> int:
    current = 0
    longest = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def aggregate_daily_values(
    daily: Mapping[str, list[Any]],
) -> dict[int, dict[str, float | int]]:
    """Aggregate one model's daily values into yearly THI indicators."""

    required = ("time",) + DAILY_VARIABLES
    if any(key not in daily for key in required):
        raise ClimateProfileGenerationError("日別モデル値に必要な項目がありません。")
    lengths = {len(daily[key]) for key in required}
    if len(lengths) != 1:
        raise ClimateProfileGenerationError("日別モデル値の配列長が一致しません。")

    values_by_year: dict[int, list[tuple[float, float, float, float, float]]] = {}
    for observed_on, temperature, maximum, humidity, wind in zip(
        daily["time"],
        daily["temperature_2m_mean"],
        daily["temperature_2m_max"],
        daily["relative_humidity_2m_mean"],
        daily["wind_speed_10m_mean"],
        strict=True,
    ):
        if None in (temperature, maximum, humidity, wind):
            continue
        temperature_value = float(temperature)
        humidity_value = float(humidity)
        year = int(str(observed_on)[:4])
        values_by_year.setdefault(year, []).append(
            (
                temperature_value,
                float(maximum),
                humidity_value,
                float(wind),
                calculate_daily_mean_thi(temperature_value, humidity_value),
            )
        )
    if not values_by_year:
        raise ClimateProfileGenerationError("利用可能な日別モデル値がありません。")

    yearly: dict[int, dict[str, float | int]] = {}
    for year, values in values_by_year.items():
        thi_days = [value[4] >= 72 for value in values]
        yearly[year] = {
            "valid_daily_values": len(values),
            "hot_days_temperature_max_ge_30": sum(value[1] >= 30 for value in values),
            "thi_days_daily_mean_ge_72": sum(thi_days),
            "max_consecutive_thi_days": _longest_consecutive(thi_days),
            "mean_temperature_c": round(sum(value[0] for value in values) / len(values), 3),
            "mean_relative_humidity_pct": round(sum(value[2] for value in values) / len(values), 3),
            "mean_outdoor_wind_speed_10m_mps": round(sum(value[3] for value in values) / len(values), 3),
        }
    return yearly


def request_url(
    latitude: float,
    longitude: float,
    model: str,
    start_year: int,
    end_year: int,
) -> str:
    """Build one bounded Open-Meteo Climate API model request."""

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": f"{start_year}-01-01",
        "end_date": f"{end_year}-12-31",
        "daily": ",".join(DAILY_VARIABLES),
        "models": model,
        "wind_speed_unit": "ms",
        "timezone": "Asia/Tokyo",
    }
    return f"{CLIMATE_API_URL}?{urlencode(params)}"


def build_climate_model_profile(
    *,
    region_id: str,
    region_name_ja: str,
    latitude: float,
    longitude: float,
    start_year: int,
    end_year: int,
    period_role: str,
    fetch_model: Callable[[str, str], Mapping[str, Any]],
    models: tuple[str, ...] = DEFAULT_MODELS,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Fetch through an adapter and assemble a versioned multi-model profile."""

    if start_year > end_year:
        raise ClimateProfileGenerationError("開始年は終了年以前にしてください。")
    if period_role not in {"recent_model_baseline", "future_projection"}:
        raise ClimateProfileGenerationError("モデル期間の役割が正しくありません。")

    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    retrievals: list[dict[str, Any]] = []
    values_by_model: dict[str, dict[int, dict[str, float | int]]] = {}
    for model in models:
        url = request_url(latitude, longitude, model, start_year, end_year)
        try:
            payload = fetch_model(model, url)
            daily = payload.get("daily")
            if not isinstance(daily, Mapping):
                raise ClimateProfileGenerationError("日別モデル値がありません。")
            values_by_model[model] = aggregate_daily_values(daily)
            retrievals.append(
                {
                    "model": model,
                    "status": "success",
                    "request_url": url,
                    "retrieved_at": timestamp,
                    "returned_latitude": payload.get("latitude"),
                    "returned_longitude": payload.get("longitude"),
                    "units": payload.get("daily_units", {}),
                }
            )
        except (ClimateProfileGenerationError, KeyError, OSError, TypeError, ValueError) as exc:
            retrievals.append(
                {
                    "model": model,
                    "status": "failed",
                    "request_url": url,
                    "retrieved_at": timestamp,
                    "error": str(exc),
                }
            )
    if len(values_by_model) < 4:
        raise ClimateProfileGenerationError("4モデル以上の取得成功が必要です。")

    metric_keys = (
        "hot_days_temperature_max_ge_30",
        "thi_days_daily_mean_ge_72",
        "max_consecutive_thi_days",
        "mean_temperature_c",
        "mean_relative_humidity_pct",
        "mean_outdoor_wind_speed_10m_mps",
    )
    years: dict[str, Any] = {}
    for year in range(start_year, end_year + 1):
        model_values = {
            model: yearly[year]
            for model, yearly in values_by_model.items()
            if year in yearly
        }
        if len(model_values) < 4:
            raise ClimateProfileGenerationError(f"{year}年に4モデル以上の値がありません。")
        years[str(year)] = {
            "model_values": model_values,
            "summary": {
                key: {
                    "median": round(float(median(float(value[key]) for value in model_values.values())), 3),
                    "minimum": round(min(float(value[key]) for value in model_values.values()), 3),
                    "maximum": round(max(float(value[key]) for value in model_values.values()), 3),
                }
                for key in metric_keys
            },
        }

    classification = (
        "climate_model_reference_scenario"
        if period_role == "recent_model_baseline"
        else "climate_model_projection_scenario"
    )
    return {
        "profile_id": f"{region_id}_{start_year}_{end_year}_climate_models",
        "region_id": region_id,
        "region_name_ja": region_name_ja,
        "classification": classification,
        "period_role": period_role,
        "generated_at": timestamp,
        "period": {"start_year": start_year, "end_year": end_year},
        "thi_definition": {
            "formula": "NRC daily-mean screening THI",
            "threshold": 72,
            "temperature_source": "daily temperature_2m_mean",
            "humidity_source": "daily relative_humidity_2m_mean",
            "note_ja": "日平均値による比較指標であり、日最高THIや個体診断ではありません。",
        },
        "aggregation_rules": {
            "thi_days_daily_mean_ge_72": "daily mean NRC THI >= 72",
            "model_period_note_ja": "過去年も観測値ではなくモデル検証期間です。",
            "bias_correction_note_ja": "Open-Meteo既定のERA5-Land線形バイアス補正を使用します。",
            "outdoor_wind_note_ja": "屋外10m風速は牛体付近風速ではなく、投資計算にも使用しません。",
        },
        "source": {
            "provider": "Open-Meteo Climate API",
            "dataset": "CMIP6 HighResMIP climate models",
            "provenance_kind": "processed_cmip6_api",
        },
        "retrievals": retrievals,
        "years": years,
    }

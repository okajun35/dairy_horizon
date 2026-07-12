"""Deterministic helpers for versioned future-climate screening profiles.

The web application only reads the JSON profiles created by the companion
script.  Fetching and HTTP handling deliberately live outside this module.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from statistics import median
from typing import Any
from urllib.parse import urlencode


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
    """Raised when a generated profile would be too incomplete to use."""


def daily_mean_thi(temperature_c: float, relative_humidity_pct: float) -> float:
    """Calculate the NRC screening THI from daily mean temperature/humidity."""
    return (1.8 * temperature_c + 32) - (0.55 - 0.0055 * relative_humidity_pct) * (1.8 * temperature_c - 26)


def _longest_consecutive(values: list[bool]) -> int:
    current = longest = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def aggregate_daily_values(daily: dict[str, list[Any]]) -> dict[int, dict[str, float | int]]:
    """Aggregate one model's Open-Meteo daily result into yearly indicators."""
    required = ("time",) + DAILY_VARIABLES
    if any(key not in daily for key in required):
        raise ClimateProfileGenerationError("daily climate response is missing a required variable")
    lengths = {len(daily[key]) for key in required}
    if len(lengths) != 1:
        raise ClimateProfileGenerationError("daily climate response arrays have inconsistent lengths")

    values_by_year: dict[int, list[tuple[float, float, float, float, float]]] = {}
    for date, temperature, temperature_max, humidity, wind in zip(
        daily["time"], daily["temperature_2m_mean"], daily["temperature_2m_max"],
        daily["relative_humidity_2m_mean"], daily["wind_speed_10m_mean"], strict=True,
    ):
        if None in (temperature, temperature_max, humidity, wind):
            continue
        year = int(str(date)[:4])
        temperature_float, humidity_float = float(temperature), float(humidity)
        values_by_year.setdefault(year, []).append(
            (temperature_float, float(temperature_max), humidity_float, float(wind), daily_mean_thi(temperature_float, humidity_float))
        )
    if not values_by_year:
        raise ClimateProfileGenerationError("daily climate response contains no usable values")

    result: dict[int, dict[str, float | int]] = {}
    for year, values in values_by_year.items():
        thi_days = [thi >= 72 for _, _, _, _, thi in values]
        result[year] = {
            "hot_days_temperature_max_ge_30": sum(maximum >= 30 for _, maximum, _, _, _ in values),
            "thi_days_daily_mean_ge_72": sum(thi_days),
            "max_consecutive_thi_days": _longest_consecutive(thi_days),
            "mean_temperature_c": round(sum(item[0] for item in values) / len(values), 3),
            "mean_relative_humidity_pct": round(sum(item[2] for item in values) / len(values), 3),
            "mean_outdoor_wind_speed_10m_mps": round(sum(item[3] for item in values) / len(values), 3),
        }
    return result


def request_url(latitude: float, longitude: float, model: str, start_year: int, end_year: int) -> str:
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


def build_future_profile(
    *,
    region_id: str,
    region_name_ja: str,
    latitude: float,
    longitude: float,
    start_year: int,
    end_year: int,
    fetch_model: Callable[[str, str], dict[str, Any]],
    models: tuple[str, ...] = DEFAULT_MODELS,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Fetch-model adapter boundary plus deterministic profile assembly.

    ``fetch_model`` receives model name and URL, which keeps this function
    straightforward to test with mocked HTTP responses.
    """
    retrieved: list[dict[str, Any]] = []
    by_model: dict[str, dict[int, dict[str, float | int]]] = {}
    retrieved_at = generated_at or datetime.now(timezone.utc).isoformat()
    for model in models:
        url = request_url(latitude, longitude, model, start_year, end_year)
        try:
            payload = fetch_model(model, url)
            by_model[model] = aggregate_daily_values(payload["daily"])
            retrieved.append({
                "model": model, "status": "success", "request_url": url,
                "retrieved_at": retrieved_at,
                "returned_latitude": payload.get("latitude"), "returned_longitude": payload.get("longitude"),
                "units": payload.get("daily_units", {}),
            })
        except (ClimateProfileGenerationError, KeyError, OSError, TypeError, ValueError) as exc:
            retrieved.append({"model": model, "status": "failed", "request_url": url, "retrieved_at": retrieved_at, "error": str(exc)})
    if len(by_model) < 4:
        raise ClimateProfileGenerationError("at least four climate models must be retrieved successfully")

    yearly: dict[str, Any] = {}
    metric_keys = (
        "hot_days_temperature_max_ge_30", "thi_days_daily_mean_ge_72", "max_consecutive_thi_days",
        "mean_temperature_c", "mean_relative_humidity_pct", "mean_outdoor_wind_speed_10m_mps",
    )
    for year in range(start_year, end_year + 1):
        model_values = {model: metrics[year] for model, metrics in by_model.items() if year in metrics}
        if len(model_values) < 4:
            raise ClimateProfileGenerationError(f"fewer than four valid model results for {year}")
        yearly[str(year)] = {
            "model_values": model_values,
            "summary": {
                key: {
                    "median": round(float(median([float(value[key]) for value in model_values.values()])), 3),
                    "minimum": round(min(float(value[key]) for value in model_values.values()), 3),
                    "maximum": round(max(float(value[key]) for value in model_values.values()), 3),
                }
                for key in metric_keys
            },
        }
    return {
        "profile_id": f"{region_id}_{start_year}_{end_year}_climate_models",
        "region_id": region_id,
        "region_name_ja": region_name_ja,
        "classification": "climate_model_projection_scenario",
        "generated_at": retrieved_at,
        "period": {"start_year": start_year, "end_year": end_year},
        "thi_definition": {
            "formula": "NRC daily-mean screening THI", "threshold": 72,
            "temperature_source": "daily temperature_2m_mean", "humidity_source": "daily relative_humidity_2m_mean",
            "note_ja": "日平均値による時点整合したスクリーニング指標であり、日最高THIや個体診断ではありません。",
        },
        "aggregation_rules": {
            "hot_days_temperature_max_ge_30": "daily temperature_2m_max >= 30°C",
            "thi_days_daily_mean_ge_72": "daily mean NRC THI >= 72",
            "max_consecutive_thi_days": "longest consecutive sequence of daily mean THI >= 72",
            "outdoor_wind_note_ja": "屋外10m風速は牛体付近風速ではなく、投資計算にも使用しません。",
        },
        "source": {"provider": "Open-Meteo Climate API", "dataset": "CMIP6 climate model projections", "provenance_kind": "official_projection_report"},
        "retrievals": retrieved,
        "years": yearly,
    }

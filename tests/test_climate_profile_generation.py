from __future__ import annotations

import unittest

from app.climate_profile_generation import (
    DEFAULT_MODELS,
    ClimateProfileGenerationError,
    aggregate_daily_values,
    build_climate_model_profile,
    request_url,
)


def model_payload(model: str, _: str) -> dict[str, object]:
    model_offset = DEFAULT_MODELS.index(model)
    return {
        "latitude": 35.6,
        "longitude": 140.1,
        "daily_units": {
            "temperature_2m_mean": "°C",
            "temperature_2m_max": "°C",
            "relative_humidity_2m_mean": "%",
            "wind_speed_10m_mean": "m/s",
        },
        "daily": {
            "time": ["2020-07-01", "2020-07-02", "2020-07-03"],
            "temperature_2m_mean": [20, 25, 25],
            "temperature_2m_max": [29, 30 + model_offset, 31],
            "relative_humidity_2m_mean": [70, 70, 70],
            "wind_speed_10m_mean": [3, 3, 3],
        },
    }


class ClimateProfileGenerationTest(unittest.TestCase):
    def test_daily_values_are_aggregated_with_the_shared_thi_definition(self) -> None:
        daily = model_payload(DEFAULT_MODELS[0], "")["daily"]

        result = aggregate_daily_values(daily)[2020]

        self.assertEqual(result["thi_days_daily_mean_ge_72"], 2)
        self.assertEqual(result["max_consecutive_thi_days"], 2)

    def test_model_reference_profile_records_period_role_and_each_model(self) -> None:
        profile = build_climate_model_profile(
            region_id="chiba_city",
            region_name_ja="千葉市",
            latitude=35.6074,
            longitude=140.1065,
            start_year=2020,
            end_year=2020,
            period_role="recent_model_baseline",
            fetch_model=model_payload,
            generated_at="2026-07-16T00:00:00+00:00",
        )

        self.assertEqual(profile["classification"], "climate_model_reference_scenario")
        self.assertEqual(profile["period_role"], "recent_model_baseline")
        self.assertEqual(profile["period"], {"start_year": 2020, "end_year": 2020})
        self.assertEqual(len(profile["years"]["2020"]["model_values"]), 7)
        self.assertEqual(profile["source"]["provenance_kind"], "processed_cmip6_api")

    def test_profile_requires_at_least_four_successful_models(self) -> None:
        with self.assertRaisesRegex(ClimateProfileGenerationError, "4モデル"):
            build_climate_model_profile(
                region_id="test",
                region_name_ja="試験地域",
                latitude=35.0,
                longitude=140.0,
                start_year=2020,
                end_year=2020,
                period_role="recent_model_baseline",
                fetch_model=model_payload,
                models=DEFAULT_MODELS[:3],
            )

    def test_request_url_uses_the_requested_baseline_period(self) -> None:
        url = request_url(35.6074, 140.1065, DEFAULT_MODELS[0], 2020, 2025)

        self.assertIn("start_date=2020-01-01", url)
        self.assertIn("end_date=2025-12-31", url)
        self.assertIn("relative_humidity_2m_mean", url)


if __name__ == "__main__":
    unittest.main()

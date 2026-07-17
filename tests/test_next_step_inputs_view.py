from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from app.main import app


def _next_step(html: str) -> str:
    match = re.search(
        r'<section class="next-step[^\"]*" id="next-step".*?</section>',
        html,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("next-step section was not rendered")
    return match.group(0)


class NextStepInputsViewTest(unittest.TestCase):
    def test_next_question_progresses_through_the_three_confirmation_values(self) -> None:
        client = TestClient(app)

        future = _next_step(client.get("/check").text)
        coverage = _next_step(client.get("/check?future_target_cow_count=45").text)
        milk = _next_step(
            client.get(
                "/check?future_target_cow_count=45"
                "&confirmed_covered_cow_count=12"
            ).text
        )
        complete = _next_step(
            client.get(
                "/check?future_target_cow_count=45"
                "&confirmed_covered_cow_count=12"
                "&avoided_milk_loss_kg_per_cow_day=2.5"
            ).text
        )

        self.assertIn('data-primary-input="future_target_cow_count"', future)
        self.assertIn('data-primary-input="confirmed_covered_cow_count"', coverage)
        self.assertIn(
            'data-primary-input="avoided_milk_loss_kg_per_cow_day"', milk
        )
        self.assertIn('data-next-step-complete="true"', complete)

    def test_all_result_side_inputs_are_in_one_anchor_returning_form(self) -> None:
        response = TestClient(app).get(
            "/check?future_target_cow_count=45"
            "&confirmed_covered_cow_count=12"
            "&avoided_milk_loss_kg_per_cow_day=2.5"
            "&milk_price_yen_per_kg=150"
            "&electricity_price_yen_per_kwh=30"
            "&operating_hours_per_day=12"
            "&current_annual_shipped_milk_kg=600000"
            "&future_annual_shipped_milk_kg=450000"
            "&first_phase_fan_count=4"
            "&planned_fan_count=18"
            "&investment_year=2028"
        )

        section = _next_step(response.text)
        self.assertIn(
            '<form class="next-step-inputs" method="get" action="/check#next-step">',
            section,
        )
        for input_name in (
            "future_target_cow_count",
            "confirmed_covered_cow_count",
            "avoided_milk_loss_kg_per_cow_day",
            "milk_price_yen_per_kg",
            "electricity_price_yen_per_kwh",
            "operating_hours_per_day",
            "current_annual_shipped_milk_kg",
            "future_annual_shipped_milk_kg",
            "first_phase_fan_count",
            "planned_fan_count",
            "investment_year",
        ):
            self.assertIn(f'name="{input_name}"', section)

        self.assertNotIn('<form class="future-herd-control"', response.text)
        self.assertNotIn('<form class="coverage-control"', response.text)
        self.assertNotIn('<form class="operating-hours-control"', response.text)
        self.assertNotIn('<form class="first-phase-control"', response.text)

    def test_reference_state_asks_for_actual_fan_count_in_the_same_place(self) -> None:
        section = _next_step(
            TestClient(app).get(
                "/check?lactating_cows=100&lane_count=4"
                "&existing_fan_count=34&reference_mode=true"
            ).text
        )

        self.assertIn('data-primary-input="existing_fan_count"', section)
        self.assertIn("現在使っているファンは何台ですか？", section)
        self.assertNotIn('name="reference_mode"', section)

    def test_blank_standard_placeholders_do_not_skip_the_next_question(self) -> None:
        client = TestClient(app)
        common_blank_details = {
            "confirmed_covered_cow_count": "",
            "operating_hours_per_day": "",
            "avoided_milk_loss_kg_per_cow_day": "",
            "milk_price_yen_per_kg": "",
            "electricity_price_yen_per_kwh": "",
        }

        after_future = client.get(
            "/check",
            params=common_blank_details | {"future_target_cow_count": "45"},
        )
        after_coverage = client.get(
            "/check",
            params=common_blank_details
            | {
                "future_target_cow_count": "45",
                "confirmed_covered_cow_count": "12",
            },
        )

        self.assertIn(
            'data-primary-input="confirmed_covered_cow_count"',
            _next_step(after_future.text),
        )
        self.assertEqual(after_future.status_code, 200)
        self.assertIn(
            'data-primary-input="avoided_milk_loss_kg_per_cow_day"',
            _next_step(after_coverage.text),
        )


if __name__ == "__main__":
    unittest.main()

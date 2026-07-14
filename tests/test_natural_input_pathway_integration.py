from __future__ import annotations

from html import unescape
import json
import re
import unittest

from fastapi.testclient import TestClient

from app.main import app, get_natural_input_interpreter
from app.natural_input import NaturalInputCandidate


def _viewer_payload(response_text: str) -> dict[str, object]:
    match = re.search(
        r'<script id="barn-payload" type="application/json">(.*?)</script>',
        response_text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("barn payload was not rendered")
    return json.loads(unescape(match.group(1)))


def _candidate_form_values(response_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in ("region_ja", "lactating_cows", "lane_count", "existing_fan_count"):
        match = re.search(rf'name="{field}"[^>]*value="([^"]*)"', response_text)
        if match is None:
            raise AssertionError(f"candidate field was not rendered: {field}")
        values[field] = unescape(match.group(1))
    return values


def _paths_by_key(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    comparison = payload["path_comparison"]
    assert isinstance(comparison, dict)
    paths = comparison["paths"]
    assert isinstance(paths, list)
    return {path["key"]: path for path in paths if isinstance(path, dict)}


class NaturalInputPathwayIntegrationTest(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_confirmed_75_cow_candidates_drive_all_three_annual_paths(self) -> None:
        class FakeInterpreter:
            def interpret(self, _text: str) -> NaturalInputCandidate:
                return NaturalInputCandidate("十勝", 75, 2, 12, ())

        app.dependency_overrides[get_natural_input_interpreter] = lambda: FakeInterpreter()
        client = TestClient(app)

        candidate_response = client.post(
            "/interpret",
            data={"farm_description": "十勝で75頭、2列、既存ファン12台"},
        )
        unconfirmed_payload = _viewer_payload(candidate_response.text)
        confirmed_values = _candidate_form_values(candidate_response.text)
        confirmed_response = client.get("/", params=confirmed_values)
        confirmed_payload = _viewer_payload(confirmed_response.text)
        paths = _paths_by_key(confirmed_payload)

        self.assertEqual(unconfirmed_payload["inputs"]["lactating_cows"], 60)
        self.assertEqual(confirmed_payload["inputs"]["region_ja"], "十勝")
        self.assertEqual(confirmed_payload["inputs"]["lactating_cows"], 75)
        self.assertEqual(confirmed_payload["guideline_fan_count"], 25)
        self.assertEqual(confirmed_payload["guideline_gap_fan_count"], 13)

        current = paths["current"]
        first_phase = paths["first_phase"]
        full_coverage = paths["full_coverage"]
        self.assertEqual([year["uncovered_cow_count"] for year in current["years"]], [39] * 5)
        self.assertEqual(current["cumulative_uncovered_cow_years"], 195)
        self.assertEqual([year["active_fan_count"] for year in first_phase["years"]], [17] * 5)
        self.assertEqual([year["uncovered_cow_count"] for year in first_phase["years"]], [24] * 5)
        self.assertEqual(first_phase["cumulative_uncovered_cow_years"], 120)
        self.assertEqual(first_phase["review_year"], 2027)
        self.assertEqual(first_phase["next_decision_status"], "pending_observation")
        self.assertEqual([year["uncovered_cow_count"] for year in full_coverage["years"]], [0] * 5)
        self.assertEqual(full_coverage["cumulative_uncovered_cow_years"], 0)

    def test_later_year_and_custom_first_phase_stay_synchronized_after_confirmation(self) -> None:
        response = TestClient(app).get(
            "/",
            params={
                "region_ja": "十勝",
                "lactating_cows": 75,
                "lane_count": 2,
                "existing_fan_count": 12,
                "first_phase_fan_count": 4,
                "investment_year": 2028,
            },
        )
        payload = _viewer_payload(response.text)
        paths = _paths_by_key(payload)
        first_phase = paths["first_phase"]
        full_coverage = paths["full_coverage"]

        self.assertEqual([year["active_fan_count"] for year in first_phase["years"]], [12, 12, 16, 16, 16])
        self.assertEqual([year["investment_fan_count"] for year in first_phase["years"]], [0, 0, 4, 0, 0])
        self.assertEqual([year["uncovered_cow_count"] for year in first_phase["years"]], [39, 39, 27, 27, 27])
        self.assertEqual(first_phase["cumulative_uncovered_cow_years"], 159)
        self.assertEqual(first_phase["review_year"], 2029)
        self.assertEqual([year["uncovered_cow_count"] for year in full_coverage["years"]], [39, 39, 0, 0, 0])
        self.assertEqual(full_coverage["cumulative_uncovered_cow_years"], 78)
        self.assertIn('name="region_ja" type="hidden" value="十勝"', response.text)

    def test_confirmed_no_shortage_input_has_no_investment_event_or_false_pending_state(self) -> None:
        response = TestClient(app).get(
            "/",
            params={
                "region_ja": "千葉市",
                "lactating_cows": 60,
                "lane_count": 2,
                "existing_fan_count": 20,
            },
        )
        paths = _paths_by_key(_viewer_payload(response.text))

        for path in paths.values():
            self.assertIsNone(path["investment_year"])
            self.assertIsNone(path["review_year"])
            self.assertEqual(path["next_decision_status"], "comparison_only")
            self.assertEqual(path["cumulative_uncovered_cow_years"], 0)
            self.assertTrue(all(year["investment_fan_count"] == 0 for year in path["years"]))


if __name__ == "__main__":
    unittest.main()

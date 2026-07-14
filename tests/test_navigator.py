from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import _dashboard, app
from app.navigator import BarnInput, build_navigation, guideline_fan_count


class NavigatorTest(unittest.TestCase):
    def test_headcount_guideline_rounds_only_the_total_cow_count(self) -> None:
        cases = {1: 1, 3: 1, 4: 2, 30: 10, 60: 20, 61: 21}

        for cow_count, expected in cases.items():
            with self.subTest(cow_count=cow_count):
                self.assertEqual(guideline_fan_count(cow_count), expected)

    def test_dashboard_contract_contains_path_comparison(self) -> None:
        dashboard = _dashboard(60, 2, 10, None, 2026)

        self.assertIn("path_comparison", dashboard)
        self.assertIn("path_comparison", dashboard["viewer_payload"])
        self.assertEqual(dashboard["path_comparison"].start_year, 2026)
        self.assertEqual(dashboard["path_comparison"].end_year, 2030)

    def test_60_cows_has_20_required_fans_and_10_fan_gap(self) -> None:
        result = build_navigation(BarnInput(60, 2, 10))
        self.assertEqual(result.guideline_fans_by_lane_for_display, (10, 10))
        self.assertEqual(result.guideline_gap_fan_count, 10)
        self.assertEqual(len(result.plans[0].covered_cow_ids), 30)
        self.assertEqual(result.plans[1].additional_fan_count, 5)
        self.assertEqual(len(result.plans[1].newly_covered_cow_ids), 15)

        current = result.current_state
        self.assertEqual(current.guideline_fan_count, 20)
        self.assertEqual(current.guideline_fans_by_lane_for_display, (10, 10))
        self.assertEqual(current.existing_fan_count, 10)
        self.assertEqual(current.guideline_gap_fan_count, 10)
        self.assertEqual(current.assumed_existing_fans_by_lane, (5, 5))
        self.assertEqual(len(current.estimated_covered_cow_ids), 30)
        self.assertEqual(len(current.estimated_uncovered_cow_ids), 30)
        self.assertEqual(current.fan_capacity_cows_per_unit, 3)
        self.assertEqual(current.coverage_basis_kind, "industry_guidance")
        self.assertEqual(current.coverage_source_id, "zenrakuren_cowbell_178")
        self.assertEqual(current.placement_basis_kind, "demo_assumption")
        self.assertTrue(current.needs_field_confirmation)

    def test_first_phase_case_can_be_changed_within_the_shortage(self) -> None:
        result = build_navigation(BarnInput(60, 2, 10, first_phase_fan_count=3))
        self.assertEqual(result.plans[1].additional_fan_count, 3)
        self.assertEqual(len(result.plans[1].newly_covered_cow_ids), 9)

    def test_75_cows_are_split_deterministically(self) -> None:
        result = build_navigation(BarnInput(75, 2, 12))
        self.assertEqual(tuple(len(lane) for lane in result.cows_by_lane), (38, 37))
        self.assertEqual(result.guideline_fan_count, 25)

    def test_six_lane_barn_is_split_and_calculated_deterministically(self) -> None:
        result = build_navigation(BarnInput(60, 6, 10))

        self.assertEqual(tuple(len(lane) for lane in result.cows_by_lane), (10, 10, 10, 10, 10, 10))
        self.assertEqual(result.guideline_fans_by_lane_for_display, (4, 4, 3, 3, 3, 3))
        self.assertEqual(result.guideline_fan_count, 20)
        self.assertEqual(result.current_state.assumed_existing_fans_by_lane, (2, 2, 2, 2, 1, 1))
        self.assertEqual(len(result.current_state.estimated_uncovered_cow_ids), 30)

    def test_guideline_count_does_not_change_with_layout_row_count(self) -> None:
        self.assertEqual(build_navigation(BarnInput(60, 2, 10)).current_state.guideline_fan_count, 20)
        self.assertEqual(build_navigation(BarnInput(60, 6, 10)).current_state.guideline_fan_count, 20)
        self.assertEqual(guideline_fan_count(60), 20)

    def test_user_planned_total_is_kept_separate_from_guideline_and_existing_fans(self) -> None:
        result = build_navigation(BarnInput(60, 6, 10, planned_fan_count=24))

        self.assertEqual(result.current_state.guideline_fan_count, 20)
        self.assertEqual(result.evaluation_fan_count, 24)
        self.assertEqual(result.evaluation_additional_fan_count, 14)
        self.assertEqual(result.fan_count_basis, "user_input")

        response = TestClient(app).get(
            "/?lactating_cows=60&lane_count=6&existing_fan_count=10&planned_fan_count=24"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("頭数基準の台数目安</dt><dd>20台", response.text)
        self.assertIn('name="planned_fan_count" type="number" min="10" value="24"', response.text)
        self.assertIn("既存10台との差分を、今回追加する台数として比較します。", response.text)

    def test_missing_planned_total_uses_the_headcount_guideline(self) -> None:
        result = build_navigation(BarnInput(60, 6, 10))

        self.assertEqual(result.evaluation_fan_count, 20)
        self.assertEqual(result.evaluation_additional_fan_count, 10)
        self.assertEqual(result.fan_count_basis, "zenrakuren_headcount_guideline")

        response = TestClient(app).get(
            "/?lactating_cows=60&lane_count=2&existing_fan_count=10&planned_fan_count="
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("頭数目安まで追加", response.text)

    def test_no_extra_fans_is_not_an_investment_success(self) -> None:
        result = build_navigation(BarnInput(60, 2, 20))
        self.assertTrue(all(plan.status == "NOT_REQUIRED" for plan in result.plans))
        self.assertTrue(all(plan.additional_fan_count == 0 for plan in result.plans))
        self.assertEqual(result.current_state.estimated_uncovered_cow_ids, ())

    def test_screen_contains_barn_and_evidence(self) -> None:
        response = TestClient(app).get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="current-barn-viewer"', response.text)
        self.assertIn('id="comparison-barn-viewer"', response.text)
        self.assertIn("現在の牛舎", response.text)
        self.assertIn("比較後の牛舎", response.text)
        self.assertIn("比較するとどう変わるか", response.text)
        self.assertIn("data-selected-uncovered", response.text)
        self.assertIn("標準仮定・計算根拠", response.text)
        self.assertIn("頭数基準の台数目安", response.text)
        self.assertIn('name="planned_fan_count"', response.text)
        self.assertIn("列数による自動補正や2列共用による半減は行いません", response.text)
        self.assertIn("industry_guidance", response.text)
        self.assertIn("全酪連 COW BELL No.178", response.text)
        self.assertIn("均等配置", response.text)
        self.assertIn('name="first_phase_fan_count"', response.text)
        self.assertIn('name="investment_year"', response.text)
        self.assertIn('<option value="6">6列</option>', response.text)
        self.assertIn("5年間の経路比較", response.text)
        self.assertIn("未カバー累計", response.text)
        self.assertIn("75頭年", response.text)
        self.assertIn("2027年夏に見直す", response.text)
        self.assertIn("data-selected-cumulative", response.text)
        self.assertIn("将来気候から投資年や台数は決めません", response.text)
        self.assertNotIn("見積依頼文", response.text)

    def test_changed_first_phase_opens_the_first_phase_view(self) -> None:
        response = TestClient(app).get("/?lactating_cows=60&lane_count=2&existing_fan_count=10&first_phase_fan_count=3")
        self.assertEqual(response.status_code, 200)
        self.assertIn('"selected_plan": "first_phase"', response.text)

    def test_later_investment_year_updates_pathway_totals(self) -> None:
        response = TestClient(app).get(
            "/?lactating_cows=60&lane_count=2&existing_fan_count=10&investment_year=2028"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('<option value="2028" selected>2028年</option>', response.text)
        self.assertIn("105頭年", response.text)
        self.assertIn("60頭年", response.text)
        self.assertIn("2029年夏に見直す", response.text)

    def test_invalid_barn_input_fallback_still_renders_pathway(self) -> None:
        response = TestClient(app).get("/?lane_count=7")

        self.assertEqual(response.status_code, 200)
        self.assertIn("牛床列数は1〜6列で入力してください。", response.text)
        self.assertIn("2026〜2030年の5年間の経路比較", response.text)
        self.assertIn("75頭年", response.text)


if __name__ == "__main__":
    unittest.main()

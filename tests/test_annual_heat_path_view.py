from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from app.main import app


def _path_card(html: str, key: str) -> str:
    match = re.search(
        rf'<article data-annual-heat-path="{key}".*?</article>',
        html,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"annual heat path was not rendered: {key}")
    return match.group(0)


class AnnualHeatPathViewTest(unittest.TestCase):
    def test_shows_no_action_loss_before_showing_equipment_burden(self) -> None:
        response = TestClient(app).get(
            "/check?avoided_milk_loss_kg_per_cow_day=3"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("何もしない場合の損失と、追加後の改善を比べる", response.text)

        no_action = _path_card(response.text, "current")
        self.assertIn("追加なし", no_action)
        self.assertIn("未カバー推計</dt><dd>30頭", no_action)
        self.assertIn("防げない乳量</dt><dd>8,753kg", no_action)
        self.assertIn("乳代売上への影響</dt><dd>-1,181,588円", no_action)
        self.assertIn("何もしない場合の基準", no_action)

        first_phase = _path_card(response.text, "first_phase")
        self.assertIn("未カバー推計</dt><dd>15頭", first_phase)
        self.assertIn("設備の年間負担</dt><dd>-282,870円", first_phase)
        self.assertIn("何もしない場合との差</dt><dd", first_phase)
        self.assertIn("-46,552円", first_phase)
        self.assertIn("annual-path-improvement-negative", first_phase)

    def test_confirmed_larger_milk_difference_turns_improvement_green(self) -> None:
        response = TestClient(app).get(
            "/check?avoided_milk_loss_kg_per_cow_day=4"
        )

        first_phase = _path_card(response.text, "first_phase")
        full_coverage = _path_card(response.text, "full_coverage")
        self.assertIn("+32,220円", first_phase)
        self.assertIn("+64,440円", full_coverage)
        self.assertIn("annual-path-improvement-positive", first_phase)
        self.assertIn("何もしない場合より改善", first_phase)
        self.assertIn("農場全体の黒字を示すものではありません", response.text)


if __name__ == "__main__":
    unittest.main()

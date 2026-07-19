from __future__ import annotations

import unittest
from decimal import Decimal

from app.answer_delta import build_answer_delta
from app.main import _dashboard


class AnswerDeltaTest(unittest.TestCase):
    def test_future_herd_answer_changes_only_future_comparison(self) -> None:
        previous = _dashboard(60, 2, 10, None, 2026)
        current = _dashboard(
            60, 2, 10, None, 2026, future_target_cow_count=45
        )

        delta = build_answer_delta(
            previous, current, "future_target_cow_count"
        )

        self.assertEqual(delta["changed"][0], {
            "label_ja": "5年後の対策対象頭数",
            "before_ja": "未確認",
            "after_ja": "45頭",
        })
        self.assertIn("現在の不足", delta["unchanged"])
        self.assertIn("第1期の追加台数", delta["unchanged"])
        self.assertIn("第1期の導入費", delta["unchanged"])

    def test_operating_hours_answer_does_not_change_fan_count_or_capex(self) -> None:
        previous = _dashboard(60, 2, 10, None, 2026)
        current = _dashboard(
            60,
            2,
            10,
            None,
            2026,
            operating_hours_per_day=Decimal("12"),
        )

        delta = build_answer_delta(previous, current, "operating_hours")

        self.assertIn(
            {
                "label_ja": "暑い日の平均運転時間",
                "before_ja": "24時間／日",
                "after_ja": "12時間／日",
            },
            delta["changed"],
        )
        self.assertIn("第1期の年間電気代", [item["label_ja"] for item in delta["changed"]])
        self.assertIn("第1期の追加台数", delta["unchanged"])
        self.assertIn("第1期の導入費", delta["unchanged"])


if __name__ == "__main__":
    unittest.main()

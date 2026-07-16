from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app


class LandingViewTest(unittest.TestCase):
    def test_landing_explains_the_product_before_starting_the_check(self) -> None:
        response = TestClient(app).get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("自分で判断するための指標をつくる", response.text)
        self.assertIn("現在相当（2020〜2025年）", response.text)
        self.assertIn("近未来（2026〜2030年）", response.text)
        self.assertIn("次の期間（2031〜2034年）", response.text)
        self.assertIn('href="/check?future_target_cow_count=45"', response.text)
        self.assertIn("60頭から5年後45頭のデモを見る", response.text)
        self.assertIn('href="/check"', response.text)
        self.assertIn("自分の牛舎で確認する", response.text)
        self.assertNotIn('id="current-barn-viewer"', response.text)

    def test_check_page_keeps_the_deterministic_barn_result(self) -> None:
        response = TestClient(app).get("/check")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AIと一緒に条件を整理する", response.text)
        self.assertIn('id="current-barn-viewer"', response.text)
        self.assertIn('action="/check"', response.text)


if __name__ == "__main__":
    unittest.main()

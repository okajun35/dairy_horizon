from __future__ import annotations

import json
import os
import unittest

import httpx

from app.natural_input import (
    NaturalInputUnavailable,
    OpenAINaturalInputInterpreter,
)


def _response_payload(output: dict[str, object]) -> dict[str, object]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(output, ensure_ascii=False),
                    }
                ],
            }
        ],
    }


class OpenAINaturalInputInterpreterTest(unittest.TestCase):
    def test_extracts_four_candidates_with_structured_outputs(self) -> None:
        captured_request: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_request.update(json.loads(request.content))
            return httpx.Response(
                200,
                json=_response_payload(
                    {
                        "region_ja": "千葉市",
                        "lactating_cows": 60,
                        "lane_count": 2,
                        "existing_fan_count": 10,
                        "missing_fields": [],
                    }
                ),
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        interpreter = OpenAINaturalInputInterpreter("test-key", "gpt-5.6-luna", client=client)

        result = interpreter.interpret("千葉で60頭、2列、ファン10台")

        self.assertEqual(result.region_ja, "千葉市")
        self.assertEqual(result.lactating_cows, 60)
        self.assertEqual(result.lane_count, 2)
        self.assertEqual(result.existing_fan_count, 10)
        self.assertEqual(result.missing_fields, ())
        self.assertEqual(result.source_kind, "user_input_candidate")
        self.assertEqual(captured_request["model"], "gpt-5.6-luna")
        self.assertFalse(captured_request["store"])
        self.assertEqual(captured_request["reasoning"], {"effort": "none"})
        self.assertEqual(captured_request["text"]["format"]["type"], "json_schema")
        self.assertTrue(captured_request["text"]["format"]["strict"])
        self.assertNotIn("tools", captured_request)

    def test_out_of_range_or_missing_values_remain_unconfirmed(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_response_payload(
                    {
                        "region_ja": "北海道",
                        "lactating_cows": 0,
                        "lane_count": None,
                        "existing_fan_count": 8,
                        "missing_fields": ["lane_count"],
                    }
                ),
            )

        interpreter = OpenAINaturalInputInterpreter(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        result = interpreter.interpret("北海道、ファン8台")

        self.assertIsNone(result.lactating_cows)
        self.assertIsNone(result.lane_count)
        self.assertEqual(result.missing_fields, ("lactating_cows", "lane_count"))

    def test_api_errors_are_mapped_to_safe_unavailable_error(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "secret provider detail"}})

        interpreter = OpenAINaturalInputInterpreter(
            "test-key",
            "gpt-5.6-luna",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        with self.assertRaisesRegex(NaturalInputUnavailable, "自然文の読み取りを利用できません") as caught:
            interpreter.interpret("千葉で60頭")

        self.assertNotIn("secret provider detail", str(caught.exception))


@unittest.skipUnless(
    os.getenv("RUN_OPENAI_INTEGRATION_TESTS") == "1",
    "Set RUN_OPENAI_INTEGRATION_TESTS=1 to call the live OpenAI API.",
)
class OpenAINaturalInputLiveTest(unittest.TestCase):
    def test_live_api_extracts_demo_barn(self) -> None:
        interpreter = OpenAINaturalInputInterpreter.from_environment()

        result = interpreter.interpret("千葉市で搾乳牛60頭、牛床は2列、既存ファンは10台です")

        self.assertEqual(result.region_ja, "千葉市")
        self.assertEqual(result.lactating_cows, 60)
        self.assertEqual(result.lane_count, 2)
        self.assertEqual(result.existing_fan_count, 10)
        self.assertEqual(result.missing_fields, ())


if __name__ == "__main__":
    unittest.main()

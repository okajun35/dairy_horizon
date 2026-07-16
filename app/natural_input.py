"""Natural-language candidate extraction with a strict OpenAI boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Literal, cast

import httpx


NaturalInputField = Literal[
    "region_ja",
    "lactating_cows",
    "lane_count",
    "existing_fan_count",
]
FIELD_ORDER: tuple[NaturalInputField, ...] = (
    "region_ja",
    "lactating_cows",
    "lane_count",
    "existing_fan_count",
)


@dataclass(frozen=True)
class NaturalInputCandidate:
    """Unconfirmed values extracted from one user-provided description."""

    region_ja: str | None
    lactating_cows: int | None
    lane_count: int | None
    existing_fan_count: int | None
    missing_fields: tuple[NaturalInputField, ...]
    future_target_cow_count: int | None = None
    source_kind: Literal["user_input_candidate"] = "user_input_candidate"


class NaturalInputUnavailable(RuntimeError):
    """Raised when natural-language extraction cannot safely return candidates."""


OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "region_ja": {"type": ["string", "null"]},
        "lactating_cows": {"type": ["integer", "null"]},
        "lane_count": {"type": ["integer", "null"]},
        "existing_fan_count": {"type": ["integer", "null"]},
        "future_target_cow_count": {"type": ["integer", "null"]},
        "missing_fields": {
            "type": "array",
            "items": {"type": "string", "enum": list(FIELD_ORDER)},
        },
    },
    "required": [*FIELD_ORDER, "future_target_cow_count", "missing_fields"],
}


class OpenAINaturalInputInterpreter:
    """Extract only candidate inputs; deterministic calculations stay elsewhere."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=20.0)

    @classmethod
    def from_environment(cls) -> OpenAINaturalInputInterpreter:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip()
        if not api_key or not model:
            raise NaturalInputUnavailable("自然文の読み取りを利用できません。")
        return cls(api_key, model)

    def interpret(self, text: str) -> NaturalInputCandidate:
        description = text.strip()
        if not description or len(description) > 2000 or not self._api_key or not self._model:
            raise NaturalInputUnavailable("自然文の読み取りを利用できません。")

        request_body = {
            "model": self._model,
            "instructions": (
                "あなたは酪農家が明示した農場条件だけを抽出します。"
                "地域、現在の搾乳牛頭数、牛床列数、既存ファン数を候補として返してください。"
                "利用者が将来の対策対象頭数を明示した場合だけfuture_target_cow_countへ返してください。"
                "書かれていない値は推測せずnullにし、missing_fieldsへ入れてください。"
                "必要ファン台数、投資判断、採算、将来気候は計算しないでください。"
            ),
            "input": description,
            "reasoning": {"effort": "none"},
            "max_output_tokens": 300,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "dairy_horizon_barn_input",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                }
            },
        }
        try:
            response = self._client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
            response.raise_for_status()
            payload = response.json()
            raw_candidate = json.loads(self._output_text(payload))
            if not isinstance(raw_candidate, dict):
                raise ValueError("structured output is not an object")
            return self._validated_candidate(raw_candidate)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise NaturalInputUnavailable("自然文の読み取りを利用できません。") from exc

    @staticmethod
    def _output_text(payload: object) -> str:
        if not isinstance(payload, dict) or payload.get("status") != "completed":
            raise ValueError("response did not complete")
        for item in payload.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "refusal":
                    raise ValueError("model refused the extraction")
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return cast(str, content["text"])
        raise ValueError("response has no output text")

    @staticmethod
    def _validated_candidate(raw: dict[str, object]) -> NaturalInputCandidate:
        region_raw = raw.get("region_ja")
        region = region_raw.strip()[:80] if isinstance(region_raw, str) and region_raw.strip() else None
        cows = OpenAINaturalInputInterpreter._bounded_int(raw.get("lactating_cows"), 1, 300)
        lanes = OpenAINaturalInputInterpreter._bounded_int(raw.get("lane_count"), 1, 6)
        existing = OpenAINaturalInputInterpreter._bounded_int(raw.get("existing_fan_count"), 0, 1000)
        future_target = OpenAINaturalInputInterpreter._bounded_int(
            raw.get("future_target_cow_count"), 1, 300
        )
        values = {
            "region_ja": region,
            "lactating_cows": cows,
            "lane_count": lanes,
            "existing_fan_count": existing,
        }
        missing = tuple(field for field in FIELD_ORDER if values[field] is None)
        return NaturalInputCandidate(
            region, cows, lanes, existing, missing, future_target
        )

    @staticmethod
    def _bounded_int(value: object, minimum: int, maximum: int) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if minimum <= value <= maximum else None

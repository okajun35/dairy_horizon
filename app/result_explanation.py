"""OpenAI adapter for explaining already-calculated screening results."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Literal, Mapping, cast

import httpx


NextCheckKey = Literal[
    "actual_fan_count",
    "equipment_quote",
    "summer_milk_difference",
    "current_milk_price",
    "operating_hours",
]
NEXT_CHECK_LABELS: dict[NextCheckKey, str] = {
    "actual_fan_count": "現在使っているファン台数",
    "equipment_quote": "実際の設備見積額",
    "summer_milk_difference": "夏季の実際の乳量差",
    "current_milk_price": "現在の乳価",
    "operating_hours": "暑い日の実際の運転時間",
}
NUMERIC_CLAIM_PATTERN = re.compile(
    r"[0-9０-９]|[一二三四五六七八九十百千万億兆〇零]+"
    r"(?:台|頭|円|日|年|時間|件|つ|案|割|パーセント)"
)
PROHIBITED_CLAIMS = ("おすすめ", "最適", "必ず", "投資すべき", "確実に")


class ResultExplanationUnavailable(RuntimeError):
    """Raised when an API explanation cannot be used safely."""


@dataclass(frozen=True)
class ResultExplanation:
    headline_ja: str
    interpretation_ja: str
    condition_ja: str
    next_check_key: NextCheckKey
    next_check_ja: str
    source_kind: Literal["ai_explanation", "template_fallback"]


OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline_ja": {"type": "string", "minLength": 1, "maxLength": 80},
        "interpretation_ja": {"type": "string", "minLength": 1, "maxLength": 240},
        "condition_ja": {"type": "string", "minLength": 1, "maxLength": 200},
        "next_check_key": {
            "type": "string",
            "enum": list(NEXT_CHECK_LABELS),
        },
    },
    "required": [
        "headline_ja",
        "interpretation_ja",
        "condition_ja",
        "next_check_key",
    ],
}


class OpenAIResultExplainer:
    """Explain deterministic results without calculating or rewriting numbers."""

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
    def from_environment(cls) -> OpenAIResultExplainer:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip()
        if not api_key or not model:
            raise ResultExplanationUnavailable("説明を生成できません。")
        return cls(api_key, model)

    def explain(self, result_payload: Mapping[str, Any]) -> ResultExplanation:
        if not self._api_key or not self._model:
            raise ResultExplanationUnavailable("説明を生成できません。")
        request_body = {
            "model": self._model,
            "instructions": (
                "あなたは酪農の暑熱対策スクリーニング結果を平易な日本語で説明します。"
                "入力JSONの数値はPythonで計算済みです。計算、変更、補完をしないでください。"
                "出力文にはアラビア数字、漢数字、金額、年、台数、頭数を含めないでください。"
                "数値は画面が別に表示します。単一案のおすすめ、最適化、投資年の推薦、"
                "確実な回収の断定をしないでください。成立条件と難しくなる条件を説明し、"
                "next_check_keyは結論を最も変える確認事項を一つ選んでください。"
                "reference_modeがtrueならactual_fan_countを優先し、それ以外は"
                "equipment_quote、summer_milk_difference、current_milk_price、"
                "operating_hoursの順を基本にしてください。"
            ),
            "input": json.dumps(result_payload, ensure_ascii=False, separators=(",", ":")),
            "reasoning": {"effort": "none"},
            "max_output_tokens": 500,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "dairy_horizon_result_explanation",
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
            raw = json.loads(self._output_text(response.json()))
            if not isinstance(raw, dict):
                raise ValueError("structured output is not an object")
            return self._validated_explanation(raw)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ResultExplanationUnavailable("説明を生成できません。") from exc

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
                    raise ValueError("model refused the explanation")
                if content.get("type") == "output_text" and isinstance(
                    content.get("text"), str
                ):
                    return cast(str, content["text"])
        raise ValueError("response has no output text")

    @staticmethod
    def _validated_text(value: object, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError("explanation field is not text")
        text = value.strip()
        if not text or len(text) > maximum:
            raise ValueError("explanation field is outside its length limit")
        if NUMERIC_CLAIM_PATTERN.search(text) or any(
            phrase in text for phrase in PROHIBITED_CLAIMS
        ):
            raise ValueError("explanation introduced an unsupported claim")
        return text

    @classmethod
    def _validated_explanation(cls, raw: dict[str, object]) -> ResultExplanation:
        next_key_raw = raw.get("next_check_key")
        if next_key_raw not in NEXT_CHECK_LABELS:
            raise ValueError("next check key is not allowed")
        next_key = cast(NextCheckKey, next_key_raw)
        return ResultExplanation(
            headline_ja=cls._validated_text(raw.get("headline_ja"), 80),
            interpretation_ja=cls._validated_text(raw.get("interpretation_ja"), 240),
            condition_ja=cls._validated_text(raw.get("condition_ja"), 200),
            next_check_key=next_key,
            next_check_ja=NEXT_CHECK_LABELS[next_key],
            source_kind="ai_explanation",
        )


def build_fallback_explanation(reference_mode: bool) -> ResultExplanation:
    """Return a stable explanation when the API cannot be used."""

    next_key: NextCheckKey = "actual_fan_count" if reference_mode else "equipment_quote"
    return ResultExplanation(
        headline_ja="計算結果を条件ごとに確認します。",
        interpretation_ja="牛舎の不足と追加案の変化を、将来の運転負担とは分けて確認できます。",
        condition_ja="暑熱期間にはモデル間の幅があり、年間電力費も条件によって変わります。",
        next_check_key=next_key,
        next_check_ja=NEXT_CHECK_LABELS[next_key],
        source_kind="template_fallback",
    )

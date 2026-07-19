"""OpenAI adapter for explaining already-calculated screening results."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import re
import time
from typing import Any, Callable, Literal, Mapping, TypeVar, cast

import httpx


logger = logging.getLogger(__name__)
ValidatedOutput = TypeVar("ValidatedOutput")
MAX_TRANSIENT_ATTEMPTS = 2
MAX_OUTPUT_ATTEMPTS = 2
CHOICE_SUMMARY_TIMEOUT_SECONDS = 45.0
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, *range(500, 600)})


NextCheckKey = Literal[
    "actual_fan_count",
    "operating_hours",
    "future_target_cow_count",
    "cow_level_wind_speed",
    "summer_milk_difference",
]
NEXT_CHECK_LABELS: dict[NextCheckKey, str] = {
    "actual_fan_count": "現在使っているファン台数",
    "operating_hours": "暑い日の実際の運転時間",
    "future_target_cow_count": "5年後の対策対象頭数",
    "cow_level_wind_speed": "設置候補範囲の牛体付近風速",
    "summer_milk_difference": "夏季の乳量差",
}
NUMERIC_CLAIM_PATTERN = re.compile(
    r"[0-9０-９]|[一二三四五六七八九十百千万億兆〇零]+"
    r"(?:台|頭|円|日|年|時間|件|つ|案|割|パーセント)"
)
PROHIBITED_CLAIMS = ("おすすめ", "最適", "必ず", "投資すべき", "確実に")


class ResultExplanationUnavailable(RuntimeError):
    """Raised when an API explanation cannot be used safely."""


class StructuredOutputValidationError(ValueError):
    """A safe, field-level explanation for rejecting model output in development logs."""


@dataclass(frozen=True)
class ResultExplanation:
    headline_ja: str
    interpretation_ja: str
    condition_ja: str
    next_check_key: NextCheckKey
    next_check_ja: str
    source_kind: Literal["ai_explanation", "template_fallback"]


@dataclass(frozen=True)
class ChoiceSummary:
    """The one financial guardrail that may be phrased by AI."""

    guardrail_ja: str
    source_kind: Literal["ai_summary", "template_fallback"]


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


CHOICE_SUMMARY_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "guardrail_ja": {"type": "string", "minLength": 1, "maxLength": 160},
    },
    "required": [
        "guardrail_ja",
    ],
}

# The deterministic page owns the pathway. The AI only has one short,
# non-decisive field to explain.
CHOICE_SUMMARY_TOTAL_MAX_LENGTH = 160
CHOICE_SUMMARY_FIELD_LIMITS = {
    "guardrail_ja": 160,
}


class OpenAIResultExplainer:
    """Explain deterministic results without calculating or rewriting numbers."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=20.0)
        self._sleep = sleep

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
                "annual_heat_pathは追加なしを基準にした暑熱対策単体の年間比較であり、"
                "農場全体の黒字とは解釈しないでください。"
                "decision_context.next_check_keyは決定論的コードが選んだ確認事項です。"
                "同じnext_check_keyを返し、なぜ次に確認するかを説明してください。"
                "設備見積額や見積依頼は選ばないでください。"
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
        def validate(raw: dict[str, object]) -> ResultExplanation:
            explanation = self._validated_explanation(raw)
            decision_context = result_payload.get("decision_context")
            if isinstance(decision_context, Mapping):
                expected_key = decision_context.get("next_check_key")
                if expected_key in NEXT_CHECK_LABELS and explanation.next_check_key != expected_key:
                    raise ValueError("model changed the deterministic next check")
            return explanation

        try:
            return self._generate_validated_output(request_body, validate)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ResultExplanationUnavailable("説明を生成できません。") from exc

    def summarize_choices(self, choice_payload: Mapping[str, Any]) -> ChoiceSummary:
        """Phrase the already-determined financial guardrail in plain Japanese."""

        if not self._api_key or not self._model:
            raise ResultExplanationUnavailable("比較の読み解きを生成できません。")
        request_body = {
            "model": self._model,
            "instructions": (
                "あなたは酪農の暑熱対策スクリーニングで、Pythonが決定済みの費用面のガードレールだけを平易な日本語で説明します。"
                "入力JSONのpathway_policyとeconomic_guardrail_fact_jaはPythonで決定済みです。計算、変更、補完、別の結論を出さないでください。"
                "進め方、案のおすすめ、二択、牛舎図、見積もり、次の行動、投資年、実測風速には触れません。"
                "年間比較が追加なしを下回る場合は、その事実と、農場全体の赤字や投資失敗を意味しないこと、追加費用を年間効果で回収できる確認ではないことを二文以内で示します。"
                "年間比較が追加なしを下回らない場合は、その事実と、投資回収の保証ではないことを示します。"
                "追加設備の年間比較が当てはまらない場合は、その事実だけを示します。"
                "出力文にはアラビア数字、漢数字、金額、年、台数、頭数を含めず、英語の内部値も出力しません。"
                "『おすすめ』『正しい』『投資すべき』『必ず』『見積』『相談』を使いません。"
            ),
            "input": json.dumps(choice_payload, ensure_ascii=False, separators=(",", ":")),
            "reasoning": {"effort": "high"},
            # This budget covers hidden reasoning as well as the short structured
            # response. The visible text remains bounded by the JSON Schema.
            "max_output_tokens": 4096,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "dairy_horizon_choice_summary",
                    "strict": True,
                    "schema": CHOICE_SUMMARY_SCHEMA,
                }
            },
        }
        try:
            def validate(raw: dict[str, object]) -> ChoiceSummary:
                summary = self._validated_choice_summary(raw)
                self._validate_choice_guardrail(summary, choice_payload)
                return summary

            return self._generate_validated_output(
                request_body,
                validate,
                timeout_seconds=CHOICE_SUMMARY_TIMEOUT_SECONDS,
            )
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ResultExplanationUnavailable("比較の読み解きを生成できません。") from exc

    def _generate_validated_output(
        self,
        request_body: Mapping[str, Any],
        validator: Callable[[dict[str, object]], ValidatedOutput],
        *,
        timeout_seconds: float | None = None,
    ) -> ValidatedOutput:
        """Retry one malformed or unsafe generation, never exposing it to the UI."""

        for attempt in range(MAX_OUTPUT_ATTEMPTS):
            try:
                response_payload = self._post_with_transient_retry(
                    request_body, timeout_seconds=timeout_seconds
                )
                raw = json.loads(self._output_text(response_payload))
                if not isinstance(raw, dict):
                    raise ValueError("structured output is not an object")
                return validator(raw)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                if attempt + 1 >= MAX_OUTPUT_ATTEMPTS:
                    logger.warning(
                        "OpenAI structured output was rejected after regeneration: reason=%s",
                        str(exc),
                    )
                    raise
                logger.info(
                    "OpenAI structured output was rejected; regenerating once: reason=%s",
                    str(exc),
                )
                self._sleep(0.1)
        raise AssertionError("output retry loop did not return or raise")

    def _post_with_transient_retry(
        self,
        request_body: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> object:
        """Retry only temporary HTTP and network failures with bounded backoff."""

        for attempt in range(MAX_TRANSIENT_ATTEMPTS):
            try:
                request_kwargs: dict[str, object] = {
                    "headers": {
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    "json": request_body,
                }
                if timeout_seconds is not None:
                    request_kwargs["timeout"] = timeout_seconds
                response = self._client.post(
                    "https://api.openai.com/v1/responses",
                    **request_kwargs,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                retryable = status_code in RETRYABLE_STATUS_CODES
                if retryable and attempt + 1 < MAX_TRANSIENT_ATTEMPTS:
                    delay = self._retry_delay(exc.response, attempt)
                    logger.warning(
                        "OpenAI request failed temporarily; retrying once: status=%s delay_seconds=%s",
                        status_code,
                        delay,
                    )
                    self._sleep(delay)
                    continue
                logger.warning(
                    "OpenAI request failed without retry: status=%s retryable=%s",
                    status_code,
                    retryable,
                )
                raise
            except httpx.TransportError as exc:
                if attempt + 1 < MAX_TRANSIENT_ATTEMPTS:
                    delay = self._retry_delay(None, attempt)
                    logger.warning(
                        "OpenAI connection failed temporarily; retrying once: reason=%s delay_seconds=%s",
                        type(exc).__name__,
                        delay,
                    )
                    self._sleep(delay)
                    continue
                logger.warning(
                    "OpenAI connection failed after retry: reason=%s", type(exc).__name__
                )
                raise
        raise AssertionError("transient retry loop did not return or raise")

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        """Use Retry-After when available, without holding the result page too long."""

        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(2.0, max(0.0, float(retry_after)))
                except ValueError:
                    pass
        return 0.25 * (2**attempt)

    @staticmethod
    def _output_text(payload: object) -> str:
        if not isinstance(payload, dict):
            raise ValueError("response is not an object")
        if payload.get("status") != "completed":
            incomplete_details = payload.get("incomplete_details")
            reason = (
                incomplete_details.get("reason")
                if isinstance(incomplete_details, dict)
                else None
            )
            raise ValueError(
                f"response did not complete: status={payload.get('status')} reason={reason}"
            )
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
    def _validated_text(value: object, maximum: int, *, field: str) -> str:
        if not isinstance(value, str):
            raise StructuredOutputValidationError(f"field={field} reason=not_text")
        text = value.strip()
        if not text or len(text) > maximum:
            raise StructuredOutputValidationError(
                f"field={field} reason=length actual={len(text)} maximum={maximum}"
            )
        if NUMERIC_CLAIM_PATTERN.search(text) or any(
            phrase in text for phrase in PROHIBITED_CLAIMS
        ):
            raise StructuredOutputValidationError(
                f"field={field} reason=unsupported_claim"
            )
        return text

    @classmethod
    def _validated_explanation(cls, raw: dict[str, object]) -> ResultExplanation:
        next_key_raw = raw.get("next_check_key")
        if next_key_raw not in NEXT_CHECK_LABELS:
            raise ValueError("next check key is not allowed")
        next_key = cast(NextCheckKey, next_key_raw)
        return ResultExplanation(
            headline_ja=cls._validated_text(raw.get("headline_ja"), 80, field="headline_ja"),
            interpretation_ja=cls._validated_text(raw.get("interpretation_ja"), 240, field="interpretation_ja"),
            condition_ja=cls._validated_text(raw.get("condition_ja"), 200, field="condition_ja"),
            next_check_key=next_key,
            next_check_ja=NEXT_CHECK_LABELS[next_key],
            source_kind="ai_explanation",
        )

    @classmethod
    def _validated_choice_summary(cls, raw: dict[str, object]) -> ChoiceSummary:
        texts = {
            field: cls._validated_text(raw.get(field), maximum, field=field)
            for field, maximum in CHOICE_SUMMARY_FIELD_LIMITS.items()
        }
        if sum(len(value) for value in texts.values()) > CHOICE_SUMMARY_TOTAL_MAX_LENGTH:
            raise StructuredOutputValidationError(
                "field=all reason=total_length_exceeded"
            )
        return ChoiceSummary(
            guardrail_ja=texts["guardrail_ja"],
            source_kind="ai_summary",
        )

    @staticmethod
    def _validate_choice_guardrail(
        summary: ChoiceSummary, choice_payload: Mapping[str, Any]
    ) -> None:
        """Reject an AI phrase that conflicts with the calculated guardrail."""

        policy_raw = choice_payload.get("pathway_policy")
        policy = policy_raw if isinstance(policy_raw, Mapping) else {}
        guardrail = policy.get("economic_guardrail")
        text = summary.guardrail_ja
        if guardrail in {
            "first_phase_annual_comparison_negative",
            "full_coverage_annual_comparison_negative",
        }:
            if (
                "追加なしを下回" not in text
                or "農場全体の赤字" not in text
                or "回収" not in text
            ):
                raise StructuredOutputValidationError(
                    "field=guardrail_ja reason=conflicts_with_negative_guardrail"
                )
        elif guardrail in {
            "first_phase_annual_comparison_not_negative",
            "full_coverage_annual_comparison_not_negative",
        }:
            if "追加なしを下回っていない" not in text or "保証" not in text:
                raise StructuredOutputValidationError(
                    "field=guardrail_ja reason=conflicts_with_nonnegative_guardrail"
                )
        elif guardrail == "not_applicable" and "当てはまらない" not in text:
            raise StructuredOutputValidationError(
                "field=guardrail_ja reason=conflicts_with_not_applicable_guardrail"
            )


def build_fallback_explanation(
    reference_mode: bool,
    next_check_key: NextCheckKey | None = None,
) -> ResultExplanation:
    """Return a stable explanation when the API cannot be used."""

    next_key: NextCheckKey = next_check_key or (
        "actual_fan_count" if reference_mode else "operating_hours"
    )
    return ResultExplanation(
        headline_ja="計算結果を条件ごとに確認します。",
        interpretation_ja="牛舎の不足と追加案の変化を、将来の運転負担とは分けて確認できます。",
        condition_ja="暑熱期間にはモデル間の幅があり、年間電力費も条件によって変わります。",
        next_check_key=next_key,
        next_check_ja=NEXT_CHECK_LABELS[next_key],
        source_kind="template_fallback",
    )


def build_fallback_choice_summary(
    choice_payload: Mapping[str, Any],
) -> ChoiceSummary:
    """Keep the three-choice reading useful when the API is unavailable."""

    policy_raw = choice_payload.get("pathway_policy")
    policy = policy_raw if isinstance(policy_raw, Mapping) else {}
    guardrail = policy.get("economic_guardrail")
    if guardrail == "not_applicable":
        guardrail_ja = "追加設備の年間比較は当てはまりません。"
    elif guardrail in {
        "first_phase_annual_comparison_not_negative",
        "full_coverage_annual_comparison_not_negative",
    }:
        guardrail_ja = "年間比較は追加なしを下回っていません。投資回収の保証ではありません。"
    else:
        guardrail_ja = "年間比較は追加なしを下回ります。農場全体の赤字や投資の失敗を意味しません。"
    return ChoiceSummary(
        guardrail_ja=guardrail_ja,
        source_kind="template_fallback",
    )

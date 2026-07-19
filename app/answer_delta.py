"""View data for explaining one confirmed answer without AI-generated math."""

from __future__ import annotations

from typing import Any, Literal, Mapping


AnswerKey = Literal[
    "actual_fan_count",
    "future_target_cow_count",
    "cow_level_wind_speed",
    "summer_milk_difference",
    "operating_hours",
]

ANSWER_KEYS: tuple[AnswerKey, ...] = (
    "actual_fan_count",
    "future_target_cow_count",
    "cow_level_wind_speed",
    "summer_milk_difference",
    "operating_hours",
)


def _first_phase_financial(dashboard: Mapping[str, Any]) -> Mapping[str, Any]:
    return next(
        plan
        for plan in dashboard["financial_comparison"]["plans"]
        if plan["key"] == "first_phase"
    )


def _value_change(label: str, before: str, after: str) -> dict[str, str] | None:
    if before == after:
        return None
    return {"label_ja": label, "before_ja": before, "after_ja": after}


def _keep_if_same(
    label: str, before: str, after: str, unchanged: list[str]
) -> None:
    if before == after:
        unchanged.append(label)


def build_answer_delta(
    previous: Mapping[str, Any], current: Mapping[str, Any], answered_key: AnswerKey
) -> dict[str, Any]:
    """Describe only the deterministic consequences of one answered question."""

    previous_nav = previous["navigation"]
    current_nav = current["navigation"]
    previous_adaptation = previous["two_horizon_screening"]
    current_adaptation = current["two_horizon_screening"]
    previous_financial = _first_phase_financial(previous)
    current_financial = _first_phase_financial(current)
    previous_inputs = previous["financial_inputs"]
    current_inputs = current["financial_inputs"]
    previous_operating = previous["operating_hours"]
    current_operating = current["operating_hours"]
    changed: list[dict[str, str]] = []
    unchanged: list[str] = []

    def add(change: dict[str, str] | None) -> None:
        if change is not None:
            changed.append(change)

    if answered_key == "actual_fan_count":
        add(
            _value_change(
                "現在使っているファン台数",
                f"{previous_nav.inputs.existing_fan_count}台",
                f"{current_nav.inputs.existing_fan_count}台",
            )
        )
        add(
            _value_change(
                "現在の目安との差",
                f"{previous_nav.current_state.guideline_gap_fan_count}台",
                f"{current_nav.current_state.guideline_gap_fan_count}台",
            )
        )
        add(
            _value_change(
                "現在の未カバー推計",
                f"{len(previous_nav.current_state.estimated_uncovered_cow_ids)}頭",
                f"{len(current_nav.current_state.estimated_uncovered_cow_ids)}頭",
            )
        )
        _keep_if_same(
            "搾乳牛頭数", str(previous_nav.inputs.lactating_cows), str(current_nav.inputs.lactating_cows), unchanged
        )
    elif answered_key == "future_target_cow_count":
        previous_future = previous_adaptation.future_after
        current_future = current_adaptation.future_after
        add(
            _value_change(
                "5年後の対策対象頭数",
                "未確認" if previous_future is None else f"{previous_future.target_cow_count}頭",
                "未確認" if current_future is None else f"{current_future.target_cow_count}頭",
            )
        )
        if previous_future is not None and current_future is not None:
            add(
                _value_change(
                    "5年後・第1期後の目安との差",
                    f"{previous_future.guideline_gap_fan_count}台",
                    f"{current_future.guideline_gap_fan_count}台",
                )
            )
        _keep_if_same(
            "現在の不足", f"{previous_adaptation.current_before.guideline_gap_fan_count}台", f"{current_adaptation.current_before.guideline_gap_fan_count}台", unchanged
        )
        _keep_if_same(
            "第1期の追加台数", f"{previous_financial['additional_fan_count']}台", f"{current_financial['additional_fan_count']}台", unchanged
        )
        _keep_if_same(
            "第1期の導入費", previous_financial["incremental_capex_ja"], current_financial["incremental_capex_ja"], unchanged
        )
    elif answered_key == "cow_level_wind_speed":
        add(
            _value_change(
                "回収計算に使う確認済みの対象頭数",
                "未確認" if previous_adaptation.inputs.confirmed_covered_cow_count is None else f"{previous_adaptation.inputs.confirmed_covered_cow_count}頭",
                "未確認" if current_adaptation.inputs.confirmed_covered_cow_count is None else f"{current_adaptation.inputs.confirmed_covered_cow_count}頭",
            )
        )
        add(_value_change("回収に必要な防止乳量", previous_financial["break_even_milk_ja"], current_financial["break_even_milk_ja"]))
        _keep_if_same("第1期の追加台数", f"{previous_financial['additional_fan_count']}台", f"{current_financial['additional_fan_count']}台", unchanged)
        _keep_if_same("第1期の導入費", previous_financial["incremental_capex_ja"], current_financial["incremental_capex_ja"], unchanged)
        _keep_if_same("第1期の年間電気代", previous_financial["annual_electricity_ja"], current_financial["annual_electricity_ja"], unchanged)
    elif answered_key == "summer_milk_difference":
        add(
            _value_change(
                "夏季の防止乳量差",
                f"{previous_inputs['avoided_milk_loss_kg_per_cow_day']['value_ja']}kg／頭・日",
                f"{current_inputs['avoided_milk_loss_kg_per_cow_day']['value_ja']}kg／頭・日",
            )
        )
        add(_value_change("この条件で払える目安", previous_financial["maximum_affordable_capex_ja"], current_financial["maximum_affordable_capex_ja"]))
        _keep_if_same("第1期の追加台数", f"{previous_financial['additional_fan_count']}台", f"{current_financial['additional_fan_count']}台", unchanged)
        _keep_if_same("第1期の年間電気代", previous_financial["annual_electricity_ja"], current_financial["annual_electricity_ja"], unchanged)
    else:
        add(
            _value_change(
                "暑い日の平均運転時間",
                f"{previous_operating['value_ja']}時間／日",
                f"{current_operating['value_ja']}時間／日",
            )
        )
        add(_value_change("第1期の年間電気代", previous_financial["annual_electricity_ja"], current_financial["annual_electricity_ja"]))
        add(_value_change("回収に必要な防止乳量", previous_financial["break_even_milk_ja"], current_financial["break_even_milk_ja"]))
        _keep_if_same("第1期の追加台数", f"{previous_financial['additional_fan_count']}台", f"{current_financial['additional_fan_count']}台", unchanged)
        _keep_if_same("第1期の導入費", previous_financial["incremental_capex_ja"], current_financial["incremental_capex_ja"], unchanged)

    return {
        "answered_key": answered_key,
        "changed": tuple(changed),
        "unchanged": tuple(unchanged),
    }

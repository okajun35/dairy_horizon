#!/usr/bin/env python3
"""Fetch and save bounded daily JMA observations for Chiba station 47682."""

from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.observed_climate_generation import (
    DailyObservation,
    calculate_daily_mean_thi,
    period_file_name,
    summarize_observed_period,
)


BASE_URL = "https://www.data.jma.go.jp/stats/etrn/view/daily_s1.php"
PREC_NO = "45"
BLOCK_NO = "47682"
STATION_NAME_JA = "千葉"
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


class _DailyTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_target_table = False
        self.in_cell = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "tablefix1":
            self.in_target_table = True
        elif self.in_target_table and tag == "tr":
            self.current_row = []
        elif self.in_target_table and tag == "td":
            self.in_cell = True
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_target_table and tag == "td" and self.in_cell:
            self.current_row.append(" ".join(self.current_cell))
            self.in_cell = False
        elif self.in_target_table and tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = []
        elif self.in_target_table and tag == "table":
            self.in_target_table = False


def _clean_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().replace("−", "-")


def _number(value: str) -> float | None:
    cleaned = _clean_text(value)
    if not cleaned or cleaned in {"--", "---", "///", "×", "欠測"}:
        return None
    matched = NUMBER_RE.search(cleaned)
    return float(matched.group(0)) if matched else None


def _quality_mark(value: str) -> str:
    cleaned = _clean_text(value)
    return "".join(mark for mark in (")", "]", "*", "#") if mark in cleaned)


def build_daily_url(year: int, month: int) -> str:
    return (
        f"{BASE_URL}?prec_no={PREC_NO}&block_no={BLOCK_NO}"
        f"&year={year}&month={month}&day=&view=a2"
    )


def parse_daily_html(
    html: str,
    *,
    year: int,
    month: int,
    source_url: str,
) -> tuple[DailyObservation, ...]:
    """Parse the JMA detailed daily table while preserving missing values."""

    parser = _DailyTableParser()
    parser.feed(html)
    if not parser.rows:
        raise ValueError("気象庁の日別表 tablefix1 が見つかりません。")

    observations: list[DailyObservation] = []
    days_in_month = calendar.monthrange(year, month)[1]
    for cells in parser.rows:
        cleaned = [_clean_text(cell) for cell in cells]
        day_value = _number(cleaned[0]) if cleaned else None
        if day_value is None or not day_value.is_integer():
            continue
        day = int(day_value)
        if not 1 <= day <= days_in_month:
            continue
        if len(cleaned) < 10:
            raise ValueError(f"気象庁日別表の列数が不足しています: {year}-{month:02d}-{day:02d}")
        tail = cleaned[-9:]
        mean_temperature = _number(tail[0])
        mean_humidity = _number(tail[6])
        thi = (
            calculate_daily_mean_thi(mean_temperature, mean_humidity)
            if mean_temperature is not None and mean_humidity is not None
            else None
        )
        observations.append(
            DailyObservation(
                observed_on=date(year, month, day),
                mean_temperature_c=mean_temperature,
                max_temperature_c=_number(tail[1]),
                min_temperature_c=_number(tail[3]),
                mean_vapor_pressure_hpa=_number(tail[5]),
                mean_relative_humidity_pct=mean_humidity,
                min_relative_humidity_pct=_number(tail[7]),
                thi=None if thi is None else round(thi, 2),
                temperature_quality_mark=_quality_mark(tail[0]),
                humidity_quality_mark=_quality_mark(tail[6]),
                source_url=source_url,
            )
        )
    return tuple(observations)


def fetch_html(url: str, *, timeout_seconds: int, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        request = Request(
            url,
            headers={
                "User-Agent": "Dairy-Horizon/1.0 offline-climate-data-preparation",
                "Accept-Language": "ja,en;q=0.8",
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310: fixed JMA URL
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise OSError(f"気象庁データの取得に失敗しました: {last_error}")


def _write_daily_csv(path: Path, rows: tuple[DailyObservation, ...]) -> None:
    fieldnames = (
        "date",
        "station_name_ja",
        "prec_no",
        "block_no",
        "mean_temperature_c",
        "max_temperature_c",
        "min_temperature_c",
        "mean_vapor_pressure_hpa",
        "mean_relative_humidity_pct",
        "min_relative_humidity_pct",
        "thi_daily_mean",
        "temperature_quality_mark",
        "humidity_quality_mark",
        "source_kind",
        "source_url",
    )
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "date": row.observed_on.isoformat(),
                    "station_name_ja": STATION_NAME_JA,
                    "prec_no": PREC_NO,
                    "block_no": BLOCK_NO,
                    "mean_temperature_c": row.mean_temperature_c,
                    "max_temperature_c": row.max_temperature_c,
                    "min_temperature_c": row.min_temperature_c,
                    "mean_vapor_pressure_hpa": row.mean_vapor_pressure_hpa,
                    "mean_relative_humidity_pct": row.mean_relative_humidity_pct,
                    "min_relative_humidity_pct": row.min_relative_humidity_pct,
                    "thi_daily_mean": row.thi,
                    "temperature_quality_mark": row.temperature_quality_mark,
                    "humidity_quality_mark": row.humidity_quality_mark,
                    "source_kind": "official_observation",
                    "source_url": row.source_url,
                }
            )


def _summary_payload(
    rows: tuple[DailyObservation, ...], start_year: int, end_year: int
) -> dict[str, object]:
    annual: dict[str, object] = {}
    summaries = []
    for year in range(start_year, end_year + 1):
        summary = summarize_observed_period(
            (row for row in rows if row.observed_on.year == year),
            start_date=date(year, 1, 1),
            end_date=date(year, 12, 31),
            threshold=72,
        )
        summaries.append(summary)
        annual[str(year)] = {
            "expected_days": summary.expected_days,
            "observed_days": summary.observed_days,
            "valid_thi_days": summary.valid_thi_days,
            "completeness_pct": round(summary.valid_thi_days / summary.expected_days * 100, 3),
            "missing_observation_dates": [value.isoformat() for value in summary.missing_observation_dates],
            "missing_thi_dates": [value.isoformat() for value in summary.missing_thi_dates],
            "thi_days_daily_mean_ge_72": {
                "lower_bound": summary.thi_days_lower_bound,
                "upper_bound": summary.thi_days_upper_bound,
            },
            "status": "complete" if summary.is_complete else "missing_values",
        }
    year_count = len(summaries)
    return {
        "profile_id": f"jma_chiba_{start_year}_{end_year}_daily_observations",
        "region_id": "chiba_city",
        "region_name_ja": "千葉市",
        "station_name_ja": STATION_NAME_JA,
        "station_number": BLOCK_NO,
        "classification": "official_observation",
        "period_role": "recent_observed_baseline",
        "period": {"start_year": start_year, "end_year": end_year},
        "thi_definition": {
            "formula": "NRC daily-mean screening THI",
            "threshold": 72,
            "temperature_source": "JMA daily mean temperature",
            "humidity_source": "JMA daily mean relative humidity",
        },
        "missing_value_rule": "Missing THI days are retained as lower and upper bounds; they are not counted as non-heat days.",
        "annual": annual,
        "period_summary": {
            "annual_mean_thi_days_lower_bound": round(
                sum(value.thi_days_lower_bound for value in summaries) / year_count, 3
            ),
            "annual_mean_thi_days_upper_bound": round(
                sum(value.thi_days_upper_bound for value in summaries) / year_count, 3
            ),
            "complete_years": sum(value.is_complete for value in summaries),
            "year_count": year_count,
        },
        "source": {
            "publisher": "気象庁",
            "dataset": "過去の気象データ検索 日ごとの値 詳細",
            "provenance_kind": "official_observation",
            "base_url": BASE_URL,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/observed")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    if args.start_year > args.end_year:
        parser.error("start-year は end-year 以下にしてください。")
    delay = max(args.delay, 0.5)

    rows: list[DailyObservation] = []
    total_months = (args.end_year - args.start_year + 1) * 12
    request_number = 0
    for year in range(args.start_year, args.end_year + 1):
        for month in range(1, 13):
            request_number += 1
            url = build_daily_url(year, month)
            print(f"[{request_number}/{total_months}] {year}-{month:02d}")
            rows.extend(
                parse_daily_html(
                    fetch_html(url, timeout_seconds=args.timeout, retries=args.retries),
                    year=year,
                    month=month,
                    source_url=url,
                )
            )
            if request_number < total_months:
                time.sleep(delay)

    ordered_rows = tuple(sorted(rows, key=lambda row: row.observed_on))
    payload = _summary_payload(ordered_rows, args.start_year, args.end_year)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    daily_path = args.output_dir / period_file_name(
        "jma_chiba_daily", args.start_year, args.end_year, "csv"
    )
    summary_path = args.output_dir / period_file_name(
        "jma_chiba_thi_summary", args.start_year, args.end_year, "json"
    )
    _write_daily_csv(daily_path, ordered_rows)
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(daily_path)
    print(summary_path)
    incomplete = payload["period_summary"]["complete_years"] != payload["period_summary"]["year_count"]
    if incomplete:
        print("欠測を検出しました。日数は下限・上限で保存しています。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

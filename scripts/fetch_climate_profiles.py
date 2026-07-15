#!/usr/bin/env python3
"""Generate a versioned Open-Meteo CMIP6 profile outside the web request path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.climate_profile_generation import (
    ClimateProfileGenerationError,
    build_climate_model_profile,
)


REGIONS = {
    "chiba_city": {
        "region_name_ja": "千葉市",
        "latitude": 35.6074,
        "longitude": 140.1065,
    }
}


def fetch_json(_: str, url: str, *, retries: int = 3) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(url, headers={"User-Agent": "Dairy-Horizon/1.0 offline-climate-data-preparation"})
            with urlopen(request, timeout=90) as response:  # nosec B310: fixed Open-Meteo URL
                return json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise OSError(f"Open-Meteo取得失敗: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region-id", choices=sorted(REGIONS), default="chiba_city")
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument(
        "--period-role",
        choices=("recent_model_baseline", "future_projection"),
        required=True,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    region = REGIONS[args.region_id]
    output = args.output or (
        ROOT
        / "data/climate_profiles/generated"
        / f"{args.region_id}_{args.start_year}_{args.end_year}.json"
    )
    try:
        profile = build_climate_model_profile(
            region_id=args.region_id,
            region_name_ja=str(region["region_name_ja"]),
            latitude=float(region["latitude"]),
            longitude=float(region["longitude"]),
            start_year=args.start_year,
            end_year=args.end_year,
            period_role=args.period_role,
            fetch_model=fetch_json,
        )
    except ClimateProfileGenerationError as exc:
        parser.error(str(exc))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

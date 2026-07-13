"""Generate a versioned Open-Meteo climate-model profile; never used by the web app."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.climate_profiles import ClimateProfileGenerationError, build_future_profile


REGIONS = {
    "chiba_city": {"region_name_ja": "千葉市", "latitude": 35.6074, "longitude": 140.1065},
    "choshi": {"region_name_ja": "銚子市", "latitude": 35.7342, "longitude": 140.8266},
    "obihiro": {"region_name_ja": "帯広市", "latitude": 42.9239, "longitude": 143.1960},
    "kumamoto": {"region_name_ja": "熊本市", "latitude": 32.8031, "longitude": 130.7079},
}


def fetch_json(_: str, url: str) -> dict:
    with urlopen(url, timeout=60) as response:  # nosec B310: fixed public API URL
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region-id", required=True, choices=sorted(REGIONS))
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--end-year", type=int, default=2050)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    region = REGIONS[args.region_id]
    latitude = args.latitude if args.latitude is not None else region["latitude"]
    longitude = args.longitude if args.longitude is not None else region["longitude"]
    output = args.output or ROOT / "data/climate_profiles/generated" / f"{args.region_id}_{args.start_year}_{args.end_year}.json"
    try:
        profile = build_future_profile(
            region_id=args.region_id, region_name_ja=region["region_name_ja"], latitude=latitude, longitude=longitude,
            start_year=args.start_year, end_year=args.end_year, fetch_model=fetch_json,
        )
    except ClimateProfileGenerationError as exc:
        parser.error(str(exc))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

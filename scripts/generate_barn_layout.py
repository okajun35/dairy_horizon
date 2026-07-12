from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TieStallBarnConfig:
    lactating_cows: int
    row_count: int
    existing_fan_count: int
    stall_pitch_m: float = 1.2
    end_margin_total_m: float = 6.0
    barn_width_m: float | None = None
    cows_per_fan: int = 3
    fan_height_m: float = 2.5
    fan_angle_deg: float = 15.0

    def validate(self) -> None:
        if self.lactating_cows < 1:
            raise ValueError("lactating_cows must be positive")
        if self.row_count not in {1, 2}:
            raise ValueError("row_count must be 1 or 2")
        if self.existing_fan_count < 0:
            raise ValueError("existing_fan_count must be non-negative")
        if self.cows_per_fan < 1:
            raise ValueError("cows_per_fan must be positive")

    @property
    def cows_per_row(self) -> tuple[int, ...]:
        base, remainder = divmod(self.lactating_cows, self.row_count)
        return tuple(
            base + (1 if row_index < remainder else 0)
            for row_index in range(self.row_count)
        )

    @property
    def stalls_per_row(self) -> int:
        return max(self.cows_per_row)

    @property
    def estimated_length_m(self) -> float:
        return (
            self.stalls_per_row * self.stall_pitch_m
            + self.end_margin_total_m
        )

    @property
    def resolved_width_m(self) -> float:
        if self.barn_width_m is not None:
            return self.barn_width_m
        return 8.0 if self.row_count == 1 else 14.0

    @property
    def target_fans_per_row(self) -> tuple[int, ...]:
        return tuple(
            math.ceil(cows / self.cows_per_fan)
            for cows in self.cows_per_row
        )

    @property
    def target_fan_count(self) -> int:
        return sum(self.target_fans_per_row)

    @property
    def additional_fan_count(self) -> int:
        return max(0, self.target_fan_count - self.existing_fan_count)


def distributed_existing_slots(
    *,
    target_count: int,
    existing_count: int,
) -> set[int]:
    if target_count <= 0 or existing_count <= 0:
        return set()
    count = min(target_count, existing_count)
    if count == 1:
        return {target_count // 2}
    return {
        round(index * (target_count - 1) / (count - 1))
        for index in range(count)
    }


class TieStallLayoutGenerator:
    def generate(self, config: TieStallBarnConfig) -> dict[str, Any]:
        config.validate()

        row_y = (4.0,) if config.row_count == 1 else (4.0, 10.0)
        fan_y = (2.5,) if config.row_count == 1 else (2.5, 11.5)

        cows: list[dict[str, Any]] = []
        target_fans: list[dict[str, Any]] = []

        for row_zero_index, cow_count in enumerate(config.cows_per_row):
            row_number = row_zero_index + 1
            for stall_zero_index in range(cow_count):
                cows.append(
                    {
                        "cow_id": (
                            f"R{row_number}-C{stall_zero_index + 1:03d}"
                        ),
                        "row": row_number,
                        "stall": stall_zero_index + 1,
                        "x_m": round(
                            config.end_margin_total_m / 2
                            + stall_zero_index * config.stall_pitch_m,
                            3,
                        ),
                        "y_m": row_y[row_zero_index],
                    }
                )

            fan_count = config.target_fans_per_row[row_zero_index]
            for fan_zero_index in range(fan_count):
                first_stall = (
                    fan_zero_index * config.cows_per_fan + 1
                )
                last_stall = min(
                    cow_count,
                    first_stall + config.cows_per_fan - 1,
                )
                group_size = last_stall - first_stall + 1
                centre_stall_zero_index = (
                    first_stall - 1 + (group_size - 1) / 2
                )
                target_fans.append(
                    {
                        "fan_id": f"TARGET-{len(target_fans) + 1:03d}",
                        "row_target": row_number,
                        "x_m": round(
                            config.end_margin_total_m / 2
                            + centre_stall_zero_index
                            * config.stall_pitch_m,
                            3,
                        ),
                        "y_m": fan_y[row_zero_index],
                        "height_m": config.fan_height_m,
                        "angle_deg": config.fan_angle_deg,
                        "target_stalls": list(
                            range(first_stall, last_stall + 1)
                        ),
                    }
                )

        installed_slots = distributed_existing_slots(
            target_count=len(target_fans),
            existing_count=config.existing_fan_count,
        )
        for index, fan in enumerate(target_fans):
            fan["installed_in_current_state"] = index in installed_slots
            fan["status"] = (
                "existing" if index in installed_slots else "additional"
            )

        return {
            "input": {
                "lactating_cows": config.lactating_cows,
                "row_count": config.row_count,
                "existing_fan_count": config.existing_fan_count,
            },
            "derived": {
                "cows_per_row": list(config.cows_per_row),
                "stalls_per_row": config.stalls_per_row,
                "estimated_length_m": round(
                    config.estimated_length_m, 3
                ),
                "estimated_width_m": round(
                    config.resolved_width_m, 3
                ),
                "target_fans_per_row": list(
                    config.target_fans_per_row
                ),
                "target_fan_count": config.target_fan_count,
                "additional_fan_count": config.additional_fan_count,
            },
            "barn_boundary": {
                "length_m": round(config.estimated_length_m, 3),
                "width_m": round(config.resolved_width_m, 3),
            },
            "cows": cows,
            "fans": target_fans,
        }


def load_scenario(path: Path) -> TieStallBarnConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    barn = payload["barn_input"]
    return TieStallBarnConfig(
        lactating_cows=int(barn["lactating_cows"]),
        row_count=int(barn["row_count"]),
        existing_fan_count=int(barn["existing_fan_count"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    config = load_scenario(args.scenario)
    result = TieStallLayoutGenerator().generate(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

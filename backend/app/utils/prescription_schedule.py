"""Map consultation-style frequency_schedule codes to MAR fields."""

from __future__ import annotations

import re
from typing import Optional, Tuple, List

FOOD_TIMING_LABELS = {
    "before_food": "before food",
    "after_food": "after food",
    "with_food": "with food",
    "on_empty_stomach": "on empty stomach",
    "anytime": "anytime",
}

# frequency_schedule → (frequency code for MAR, explicit HH:MM times)
_SCHEDULE_TO_MAR: dict[str, Tuple[Optional[str], List[str]]] = {
    "1-0-0": ("OD", ["09:00"]),
    "0-1-0": (None, ["14:00"]),
    "0-0-1": ("HS", ["22:00"]),
    "1-0-1": ("BD", ["08:00", "20:00"]),
    "1-1-0": (None, ["08:00", "14:00"]),
    "1-1-1": ("TDS", ["08:00", "14:00", "20:00"]),
    "0-1-1": (None, ["14:00", "20:00"]),
}


def schedule_to_mar(frequency_schedule: Optional[str]) -> Tuple[Optional[str], List[str]]:
    key = (frequency_schedule or "1-0-0").strip()
    return _SCHEDULE_TO_MAR.get(key, ("OD", ["09:00"]))


def build_dosage_instruction(
    dosage: str,
    frequency_schedule: Optional[str] = "1-0-0",
    food_timing: Optional[str] = "after_food",
) -> str:
    schedule = (frequency_schedule or "1-0-0").strip()
    parts = schedule.split("-")
    morning = parts[0] if len(parts) > 0 else "0"
    afternoon = parts[1] if len(parts) > 1 else "0"
    night = parts[2] if len(parts) > 2 else "0"
    timings = []
    if morning == "1":
        timings.append("morning")
    if afternoon == "1":
        timings.append("afternoon")
    if night == "1":
        timings.append("night")
    frequency_text = ", ".join(timings) if timings else "once daily"
    food_label = FOOD_TIMING_LABELS.get(food_timing or "after_food", "after food")
    dose = (dosage or "1 dose").strip()
    return f"{dose} - {frequency_text} {food_label}"


def parse_duration_days(duration: Optional[str]) -> Optional[int]:
    if not duration:
        return None
    m = re.search(r"(\d+)", duration)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None

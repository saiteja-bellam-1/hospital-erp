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


def every_hours_gap(frequency_schedule: Optional[str]) -> Optional[int]:
    """Hours between doses for a q8h-style schedule."""
    match = re.fullmatch(r"q(\d+)h", (frequency_schedule or "").strip(), flags=re.IGNORECASE)
    if not match:
        return None
    hours = int(match.group(1))
    if hours < 1 or hours > 24:
        return None
    return hours


def frequency_schedule_label(frequency_schedule: Optional[str]) -> str:
    hours = every_hours_gap(frequency_schedule)
    if hours:
        unit = "hour" if hours == 1 else "hours"
        return f"Every {hours} {unit}"
    key = (frequency_schedule or "").strip()
    labels = {
        "1-0-0": "Morning only",
        "0-1-0": "Afternoon only",
        "0-0-1": "Night only",
        "1-0-1": "Morning & Night",
        "1-1-0": "Morning & Afternoon",
        "1-1-1": "Three times a day",
        "0-1-1": "Afternoon & Night",
    }
    return labels.get(key, key)


def _every_hours_times(hours: int) -> List[str]:
    """Clock times from 08:00, stepping by ``hours`` across a day."""
    start = 8 * 60
    step = hours * 60
    day = 24 * 60
    times: List[str] = []
    seen = set()
    cursor = start
    for _ in range(24):
        minutes = cursor % day
        if minutes in seen:
            break
        seen.add(minutes)
        times.append(f"{minutes // 60:02d}:{minutes % 60:02d}")
        cursor += step
    return times


def schedule_to_mar(frequency_schedule: Optional[str]) -> Tuple[Optional[str], List[str]]:
    key = (frequency_schedule or "1-0-0").strip()
    hours = every_hours_gap(key)
    if hours:
        return (f"Q{hours}H", _every_hours_times(hours))
    return _SCHEDULE_TO_MAR.get(key, ("OD", ["09:00"]))


def build_dosage_instruction(
    dosage: str,
    frequency_schedule: Optional[str] = "1-0-0",
    food_timing: Optional[str] = "after_food",
) -> str:
    schedule = (frequency_schedule or "1-0-0").strip()
    food_label = FOOD_TIMING_LABELS.get(food_timing or "after_food", "after food")
    dose = (dosage or "1 dose").strip()
    hours = every_hours_gap(schedule)
    if hours:
        unit = "hour" if hours == 1 else "hours"
        return f"{dose} - every {hours} {unit} {food_label}"
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
    return f"{dose} - {frequency_text} {food_label}"


def parse_duration_days(duration: Optional[str]) -> Optional[int]:
    """Days in '5', '5 days', '2 weeks', or '1 month'. Weeks and months are expanded."""
    if not duration:
        return None
    text = duration.strip().lower()
    if not text:
        return None
    if re.search(r"\bfortnight\b", text):
        return 14
    if re.search(r"\b(?:a|one)\s+week\b", text):
        return 7
    if re.search(r"\b(?:a|one)\s+month\b", text):
        return 30
    weeks = re.search(r"(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|w)\b", text)
    if weeks:
        return max(1, int(round(float(weeks.group(1)) * 7)))
    months = re.search(r"(\d+(?:\.\d+)?)\s*(?:months?|mons?)\b", text)
    if months:
        return max(1, int(round(float(months.group(1)) * 30)))
    days = re.search(r"(\d+(?:\.\d+)?)\s*(?:days?|d)\b", text)
    if days:
        return max(1, int(round(float(days.group(1)))))
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except ValueError:
        return None
    return value if value > 0 else None

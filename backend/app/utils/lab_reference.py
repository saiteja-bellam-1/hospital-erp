"""Helpers for lab parameter reference ranges — demographic matching, tier display, abnormal checks."""

from __future__ import annotations

from typing import Any, Optional


def _escape_html(s: str) -> str:
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_ref_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)


def uses_tiered_abnormal_check(field_type: str, matched_ranges: list[dict]) -> bool:
    """Use normal-tier abnormal logic for tiered params or multi-level descriptive ranges."""
    if field_type == "tiered_numeric":
        return True
    if len(matched_ranges) > 1:
        return any((row.get("description") or "").strip() for row in matched_ranges)
    return False


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def row_matches_demographics(row: dict, gender: Optional[str], age: Optional[float]) -> bool:
    """Return True when a reference-range row applies to the patient's gender and age."""
    r_gender = (row.get("gender") or "common").lower()
    if r_gender != "common":
        if not gender or r_gender != gender.lower():
            return False

    r_age_min = _coerce_float(row.get("age_min"))
    r_age_max = _coerce_float(row.get("age_max"))
    if age is not None and r_age_min is not None and r_age_max is not None:
        if not (r_age_min <= age <= r_age_max):
            return False
    return True


def filter_reference_ranges(
    ranges: Optional[list],
    gender: Optional[str],
    age: Optional[float],
) -> list[dict]:
    """Return demographic-matching reference rows in their configured order."""
    if not ranges:
        return []
    return [row for row in ranges if row_matches_demographics(row, gender, age)]


def match_reference_range(ranges, gender, age):
    """Find the best matching reference range entry for a patient's gender and age.

    Returns (ref_min, ref_max, description).
    Priority: exact gender+age match > gender match > common+age match > common.
    """
    if not ranges:
        return None, None, ""

    best = None
    best_score = -1
    for row in ranges:
        if not row_matches_demographics(row, gender, age):
            continue

        score = 0
        r_gender = (row.get("gender") or "common").lower()
        r_age_min = row.get("age_min")
        r_age_max = row.get("age_max")

        if gender and r_gender == gender.lower():
            score += 2
        elif r_gender == "common":
            score += 1

        if age is not None and r_age_min is not None and r_age_max is not None:
            score += 2
        elif r_age_min is None and r_age_max is None:
            score += 1

        if score > best_score:
            best_score = score
            best = row

    if not best:
        return None, None, ""

    return _coerce_float(best.get("min")), _coerce_float(best.get("max")), best.get("description", "")


def format_range_tier_text(row: dict, unit: str = "", *, html: bool = False) -> str:
    """Format one reference tier, e.g. 'Desirable Level: <150 mg/dL'."""
    desc = (row.get("description") or "").strip()
    rmin = _coerce_float(row.get("min"))
    rmax = _coerce_float(row.get("max"))
    unit_text = (unit or "").strip()
    unit_suffix = f" {_escape_html(unit_text) if html else unit_text}" if unit_text else ""

    if rmin is not None and rmax is not None:
        range_text = f"{_format_ref_number(rmin)} - {_format_ref_number(rmax)}{unit_suffix}"
    elif rmax is not None:
        lt = "&lt;" if html else "<"
        range_text = f"{lt} {_format_ref_number(rmax)}{unit_suffix}"
    elif rmin is not None:
        gt = "&gt;" if html else ">"
        range_text = f"{gt} {_format_ref_number(rmin)}{unit_suffix}"
    else:
        range_text = ""

    if desc:
        label = _escape_html(desc) if html else desc
        return f"{label}: {range_text}" if range_text else label
    return range_text or "-"


def format_reference_ranges_display(
    ranges: Optional[list],
    unit: str = "",
    *,
    html: bool = False,
    separator: str = "\n",
) -> str:
    """Join multiple tiers for report display."""
    if not ranges:
        return ""
    parts = [format_range_tier_text(row, unit, html=html) for row in ranges]
    parts = [p for p in parts if p and p != "-"]
    if not parts:
        return ""
    if html:
        return "<br/>".join(parts)
    return separator.join(parts)


def value_fits_tier(val: float, row: dict) -> bool:
    """Return True when a numeric value falls inside a single tier row."""
    rmin = _coerce_float(row.get("min"))
    rmax = _coerce_float(row.get("max"))
    if rmin is not None and rmax is not None:
        return rmin <= val <= rmax
    if rmax is not None:
        return val < rmax
    if rmin is not None:
        return val > rmin
    return True


def find_normal_tier(rows: list[dict]) -> Optional[dict]:
    """Pick the tier used for abnormal detection (explicit is_normal, else first row)."""
    if not rows:
        return None
    for row in rows:
        if row.get("is_normal"):
            return row
    return rows[0]


def is_value_abnormal_for_tiers(val: float, rows: list[dict]) -> bool:
    """Abnormal when the value does not fit the designated normal tier."""
    normal_tier = find_normal_tier(rows)
    if not normal_tier:
        return False
    return not value_fits_tier(val, normal_tier)


def is_value_abnormal_for_bounds(
    val: float,
    raw_value: str,
    field_type: str,
    ref_min: Optional[float],
    ref_max: Optional[float],
) -> bool:
    """Abnormal check for single-range field types (numeric / less_than / greater_than)."""
    if field_type == "less_than":
        return ref_max is not None and val >= ref_max
    if field_type == "greater_than":
        return ref_min is not None and val <= ref_min

    if raw_value.strip().startswith("<"):
        return ref_min is not None and val <= ref_min
    if raw_value.strip().startswith(">"):
        return ref_max is not None and val >= ref_max

    if ref_min is not None and val < ref_min:
        return True
    if ref_max is not None and val > ref_max:
        return True
    return False

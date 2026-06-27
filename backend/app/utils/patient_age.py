"""Shared patient age calculation and display helpers.

Age resolution policy:
- When date_of_birth is present, age is always derived from DOB at read/PDF time
  (years + months stay current as time passes).
- When only age/age_months are stored (no DOB), the stored values are used as-is.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Tuple


def compute_age_parts_from_dob(dob: date, ref: Optional[date] = None) -> Tuple[int, int, int]:
    """Return (years, months, total_months) from a date of birth."""
    ref = ref or date.today()
    total_months = (ref.year - dob.year) * 12 + (ref.month - dob.month)
    if ref.day < dob.day:
        total_months -= 1
    if total_months < 0:
        total_months = 0
    years = total_months // 12
    months = total_months % 12
    return years, months, total_months


def format_age_parts(
    *,
    years: Optional[int] = None,
    months: Optional[int] = None,
    total_months: Optional[int] = None,
) -> str:
    """Format age for UI and PDF display."""
    if total_months is None:
        y = years or 0
        m = months or 0
        if years is None and months is None:
            return ""
        total_months = y * 12 + m
    if total_months <= 0:
        return ""
    if total_months < 24:
        unit = "Month" if total_months == 1 else "Months"
        return f"{total_months} {unit}"
    y = total_months // 12
    m = total_months % 12
    if m == 0:
        unit = "Year" if y == 1 else "Years"
        return f"{y} {unit}"
    y_unit = "Year" if y == 1 else "Years"
    m_unit = "Month" if m == 1 else "Months"
    return f"{y} {y_unit} {m} {m_unit}"


def resolve_age_parts(patient: Any, ref: Optional[date] = None) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Resolve (years, months, total_months). Prefers DOB-derived age when available."""
    if not patient:
        return None, None, None
    dob = getattr(patient, "date_of_birth", None)
    if dob:
        return compute_age_parts_from_dob(dob, ref)
    age = getattr(patient, "age", None)
    age_months = getattr(patient, "age_months", None) or 0
    if age is not None:
        total = age * 12 + age_months
        return age, age_months, total
    if age_months:
        return 0, age_months, age_months
    return None, None, None


def patient_age_years_float(patient: Any, ref: Optional[date] = None) -> Optional[float]:
    """Age in fractional years — used for lab reference-range matching."""
    _, _, total = resolve_age_parts(patient, ref)
    if total is None:
        return None
    return total / 12.0


def patient_age_years_int(patient: Any, ref: Optional[date] = None) -> Optional[int]:
    """Whole years component of patient age."""
    years, _, _ = resolve_age_parts(patient, ref)
    return years


def format_patient_age(patient: Any, ref: Optional[date] = None) -> str:
    """Human-readable age string for UI and PDFs."""
    years, months, total = resolve_age_parts(patient, ref)
    return format_age_parts(years=years, months=months, total_months=total)


def normalize_stored_age(
    *,
    date_of_birth: Optional[date] = None,
    age: Optional[int] = None,
    age_months: Optional[int] = None,
) -> dict:
    """Compute age/age_months fields for DB storage."""
    if date_of_birth:
        years, months, _ = compute_age_parts_from_dob(date_of_birth)
        return {"age": years, "age_months": months}
    return {
        "age": age if age is not None else 0,
        "age_months": age_months or 0,
    }


def has_valid_age(
    *,
    date_of_birth: Optional[date] = None,
    age: Optional[int] = None,
    age_months: Optional[int] = None,
) -> bool:
    if date_of_birth:
        return True
    if age is not None and age > 0:
        return True
    if age_months is not None and age_months > 0:
        return True
    return False


def age_display_from_data(data: dict, *, age_key: str = "patient_age", display_key: str = "patient_age_display") -> str:
    """Resolve a display string from a PDF/API payload dict."""
    display = data.get(display_key) or data.get("age_display") or data.get("patient_age_display")
    if display:
        return str(display)
    raw_age = data.get(age_key)
    if raw_age is None or raw_age == "":
        nested = data.get("patient") or {}
        display = nested.get(display_key) or nested.get("age_display")
        if display:
            return str(display)
        raw_age = nested.get("age")
        months = nested.get("age_months")
        if raw_age is not None or months:
            return format_age_parts(
                years=int(raw_age) if raw_age is not None else 0,
                months=int(months) if months else 0,
            )
        return ""

    # Legacy payloads may pass a pre-formatted string (e.g. "5 Years").
    if isinstance(raw_age, str):
        stripped = raw_age.strip()
        if stripped and not stripped.lstrip("-").replace(".", "", 1).isdigit():
            return stripped

    try:
        years = int(raw_age)
    except (TypeError, ValueError):
        return str(raw_age)

    months = data.get("patient_age_months") or data.get("age_months")
    if months is not None:
        return format_age_parts(years=years, months=int(months))
    return format_age_parts(years=years)

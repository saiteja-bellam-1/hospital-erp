"""Aadhaar number normalisation and display.

Stored as 12 digits. Empty input is allowed. A value that is present must be
12 digits and cannot start with 0 (UIDAI numbering).
"""


def normalize_aadhaar(value):
    """Return 12 digits, None when blank, or raise ValueError."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if any(ch.isalpha() for ch in raw):
        raise ValueError("Aadhaar number must be 12 digits.")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 12 or digits[0] == "0":
        raise ValueError("Aadhaar number must be 12 digits and cannot start with 0.")
    return digits


def format_aadhaar_display(value) -> str:
    """Group a stored number as XXXX XXXX XXXX. Blank stays blank."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 12:
        return f"{digits[:4]} {digits[4:8]} {digits[8:]}"
    return raw


def aadhaar_from_payload(data) -> str:
    """Read aadhaar_number from a PDF payload, including a nested patient dict."""
    if not isinstance(data, dict):
        return ""
    raw = data.get("aadhaar_number") or ""
    if not str(raw).strip():
        nested = data.get("patient")
        if isinstance(nested, dict):
            raw = nested.get("aadhaar_number") or ""
    return format_aadhaar_display(raw)

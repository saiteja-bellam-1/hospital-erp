"""Normalize hospital phone fields to the digits MSG91 expects."""

import re


class InvalidPhone(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """Strip punctuation. A 10-digit number is treated as India (91)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 11 and digits.startswith("0"):
        return "91" + digits[1:]
    if 11 <= len(digits) <= 15:
        return digits
    raise InvalidPhone("Enter a valid mobile number with 10 to 15 digits.")

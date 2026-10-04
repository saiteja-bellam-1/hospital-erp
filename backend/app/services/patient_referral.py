"""One referral per patient.

Booking screens may collect a referral, but it is stored on the patient.
An existing patient referral is kept. A blank patient referral is filled
from the referral chosen on the first booking.
"""
from typing import Optional


def clean_referral_name(value) -> Optional[str]:
    text = (value or "").strip()
    return text[:100] or None


def apply_patient_referral(patient, incoming) -> Optional[str]:
    """Return the patient's referral, saving a booking choice when none exists."""
    saved = clean_referral_name(getattr(patient, "referred_by", None))
    if saved:
        if (patient.referred_by or "").strip() != saved:
            patient.referred_by = saved
        return saved
    chosen = clean_referral_name(incoming)
    if chosen:
        patient.referred_by = chosen
        return chosen
    return None

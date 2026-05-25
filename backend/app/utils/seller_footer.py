"""Helpers for resolving the active license's seller_info for PDF footers."""
from typing import Optional


def get_seller_info(db) -> Optional[dict]:
    """Return the seller_info dict from the most recent License row, or None.

    Safe to call from any PDF-rendering route — failures are swallowed so a
    broken license row never blocks a print.
    """
    try:
        from app.models.license import License
        lic = db.query(License).order_by(License.id.desc()).first()
        return lic.seller_info if (lic and lic.seller_info) else None
    except Exception:
        return None


def attach(hospital_info: dict, db) -> dict:
    """Mutates ``hospital_info`` to include ``seller_info`` (when available)
    and returns it for chaining."""
    if hospital_info is None:
        return hospital_info
    if 'seller_info' not in hospital_info:
        hospital_info['seller_info'] = get_seller_info(db)
    return hospital_info

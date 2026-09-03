"""Hospital app branding (name, logo, favicon) for frontend chrome."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from sqlalchemy.orm import Session

from app.models.hospital import Hospital

DEFAULT_APP_NAME = "KT HEALTH ERP"
MAX_BRANDING_BYTES = 2 * 1024 * 1024

# Landscape wordmarks (login / nav). Portrait logos overflow the header.
LOGO_CONSTRAINTS = {
    "min_width": 200,
    "max_width": 2400,
    "min_height": 40,
    "max_height": 800,
    "min_aspect_ratio": 1.0,
    "max_aspect_ratio": 6.0,
}

# Nearly square tab icons.
FAVICON_CONSTRAINTS = {
    "min_width": 32,
    "max_width": 512,
    "min_height": 32,
    "max_height": 512,
    "min_aspect_ratio": 0.9,
    "max_aspect_ratio": 1.15,
}


def branding_constraints() -> dict[str, Any]:
    return {
        "logo": {**LOGO_CONSTRAINTS, "max_bytes": MAX_BRANDING_BYTES},
        "favicon": {**FAVICON_CONSTRAINTS, "max_bytes": MAX_BRANDING_BYTES},
    }


def _format_constraints(kind: str) -> str:
    if kind == "favicon":
        c = FAVICON_CONSTRAINTS
        return (
            f"Tab icon must be nearly square, {c['min_width']}–{c['max_width']}px. "
            "Portrait or wide banners are not allowed."
        )
    c = LOGO_CONSTRAINTS
    return (
        f"Logo must be landscape (wider than tall), "
        f"{c['min_width']}–{c['max_width']}px wide and "
        f"{c['min_height']}–{c['max_height']}px tall. "
        f"Aspect ratio {c['min_aspect_ratio']:.0f}:1 to {c['max_aspect_ratio']:.0f}:1."
    )


def validate_branding_image(content: bytes, kind: str) -> tuple[int, int]:
    """Return (width, height) or raise ValueError with a user-facing message."""
    if kind not in ("logo", "favicon"):
        raise ValueError("kind must be logo or favicon")
    if len(content) > MAX_BRANDING_BYTES:
        raise ValueError("File size must be under 2MB")

    try:
        from PIL import Image

        with Image.open(BytesIO(content)) as img:
            width, height = img.size
    except Exception as exc:
        raise ValueError("Could not read image. Use PNG, JPEG, WebP, or ICO.") from exc

    if width < 1 or height < 1:
        raise ValueError("Image has invalid dimensions")

    constraints = LOGO_CONSTRAINTS if kind == "logo" else FAVICON_CONSTRAINTS
    ratio = width / height
    if (
        width < constraints["min_width"]
        or width > constraints["max_width"]
        or height < constraints["min_height"]
        or height > constraints["max_height"]
        or ratio < constraints["min_aspect_ratio"]
        or ratio > constraints["max_aspect_ratio"]
    ):
        raise ValueError(
            f"This image is {width}×{height}px. {_format_constraints(kind)}"
        )
    return width, height


def _first_hospital(db: Session) -> Hospital | None:
    return db.query(Hospital).first()


def _stock_branding(*, customisation_licensed: bool) -> dict[str, Any]:
    return {
        "name": DEFAULT_APP_NAME,
        "logo_url": None,
        "favicon_url": None,
        "customisation_licensed": customisation_licensed,
    }


def resolve_branding(
    hospital: Hospital | None,
    *,
    customisation_licensed: bool = False,
) -> dict[str, Any]:
    """Build branding payload for API responses.

    Unlicensed hospitals always get stock KT HEALTH ERP chrome even if a
    previous license left a custom name/logo in the hospital row.
    """
    if not customisation_licensed or not hospital:
        return _stock_branding(customisation_licensed=customisation_licensed)
    name = (hospital.name or "").strip() or DEFAULT_APP_NAME
    logo_url = (hospital.logo_url or "").strip() or None
    favicon_url = (hospital.favicon_url or "").strip() or None
    return {
        "name": name,
        "logo_url": logo_url,
        "favicon_url": favicon_url,
        "customisation_licensed": True,
    }


def get_branding_payload(db: Session) -> dict[str, Any]:
    from app.services.license_service import license_allows_customisation

    return resolve_branding(
        _first_hospital(db),
        customisation_licensed=license_allows_customisation(db),
    )

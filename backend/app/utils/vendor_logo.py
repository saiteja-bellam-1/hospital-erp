"""Vendor logo carried inside a signed license's seller block.

The image is written under uploads and the raw bytes are dropped before
seller_info is stored. A license with no logo clears the previous file so a
later sale without the toggle does not keep the old mark.
"""
from __future__ import annotations

import base64
import hashlib
import os

MAX_VENDOR_LOGO_BYTES = 150 * 1024
VENDOR_BRAND_DIR = "vendor-brand"

_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def _sniff_image_mime(raw: bytes) -> str | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_vendor_logo(logo: str, mime: str | None) -> tuple[bytes, str]:
    """Return (raw bytes, canonical mime) or raise ValueError."""
    text = (logo or "").strip()
    declared = (mime or "").split(";")[0].strip().lower()
    if text.startswith("data:"):
        header, _, b64part = text.partition(",")
        header_mime = header[5:].split(";")[0].strip().lower()
        if not declared:
            declared = header_mime
        text = b64part
    if declared == "image/jpg":
        declared = "image/jpeg"
    compact = "".join(text.split())
    if not compact or len(compact) > MAX_VENDOR_LOGO_BYTES * 2:
        raise ValueError("Vendor logo must be 150 KB or smaller")
    try:
        raw = base64.b64decode(compact, validate=True)
    except Exception as exc:
        raise ValueError("Vendor logo image is invalid") from exc
    if not raw or len(raw) > MAX_VENDOR_LOGO_BYTES:
        raise ValueError("Vendor logo must be 150 KB or smaller")
    sniffed = _sniff_image_mime(raw)
    if sniffed is None:
        raise ValueError("Vendor logo must be PNG, JPEG, or WebP")
    if declared and declared != sniffed:
        raise ValueError("Vendor logo type does not match the file")
    return raw, sniffed


def _clear_vendor_dir(dest_dir: str) -> None:
    if not os.path.isdir(dest_dir):
        return
    for name in os.listdir(dest_dir):
        path = os.path.join(dest_dir, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


def materialize_seller(seller: dict | None) -> dict | None:
    """Persist a vendor logo from a signed seller dict and return a storable copy.

    ``logo`` / ``logo_mime`` are removed. ``logo_url`` is set when a logo was
    written. Missing or invalid logo data clears any previously saved file.
    """
    from app.utils.paths import get_uploads_dir

    dest_dir = os.path.join(get_uploads_dir(), VENDOR_BRAND_DIR)
    if not isinstance(seller, dict):
        _clear_vendor_dir(dest_dir)
        return None

    clean = {
        key: value
        for key, value in seller.items()
        if key not in ("logo", "logo_mime", "logo_url")
    }
    logo = seller.get("logo")
    if not isinstance(logo, str) or not logo.strip():
        _clear_vendor_dir(dest_dir)
        return clean or None

    try:
        raw, mime = decode_vendor_logo(logo, seller.get("logo_mime"))
    except ValueError:
        _clear_vendor_dir(dest_dir)
        return clean or None

    ext = _MIME_EXT[mime]
    filename = f"logo-{hashlib.sha256(raw).hexdigest()[:12]}.{ext}"
    os.makedirs(dest_dir, exist_ok=True)
    _clear_vendor_dir(dest_dir)
    with open(os.path.join(dest_dir, filename), "wb") as handle:
        handle.write(raw)
    clean["logo_url"] = f"/uploads/{VENDOR_BRAND_DIR}/{filename}"
    return clean

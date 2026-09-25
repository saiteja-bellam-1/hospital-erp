"""Per-hospital room type catalog.

Built-in types are seeded on first use. Any other name is stored as a new
type so rooms, imports, and rate screens can use it.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.inpatient import RoomType

DEFAULT_ROOM_TYPES = {
    "general": "General Ward",
    "semi_private": "Semi-Private",
    "private": "Private",
    "suite": "Suite / Deluxe",
    "icu": "ICU",
    "hdu": "HDU / Step-Down",
    "nicu": "NICU",
    "picu": "PICU",
    "isolation": "Isolation",
    "labour": "Labour & Delivery",
    "recovery": "Post-Op Recovery",
    "daycare": "Day Care",
    "emergency": "Emergency / Casualty",
    "operation": "Operation Theatre",
}

_KEY_RE = re.compile(r"[^a-z0-9_]+")


def room_type_key(raw: str) -> str:
    text = (raw or "").strip().lower().replace("-", " ")
    text = "_".join(text.split())
    text = _KEY_RE.sub("", text).strip("_")[:30]
    if not text:
        raise ValueError("Room type is required")
    return text


def _label_for(raw: str, key: str) -> str:
    if key in DEFAULT_ROOM_TYPES:
        folded = (raw or "").strip().lower().replace("-", " ")
        folded = "_".join(folded.split())
        if folded == key or (raw or "").strip() == DEFAULT_ROOM_TYPES[key]:
            return DEFAULT_ROOM_TYPES[key]
    cleaned = (raw or "").strip()
    if cleaned and cleaned.lower().replace("-", "_").replace(" ", "_") != key:
        return cleaned[:100]
    return DEFAULT_ROOM_TYPES.get(key) or key.replace("_", " ").title()


def seed_room_types(db: Session, hospital_id: int) -> bool:
    """Insert the built-in types when this hospital has none. Returns True if seeded."""
    exists = (
        db.query(RoomType.id)
        .filter(RoomType.hospital_id == hospital_id)
        .first()
    )
    if exists:
        return False
    for key, label in DEFAULT_ROOM_TYPES.items():
        db.add(RoomType(
            hospital_id=hospital_id,
            key=key,
            label=label,
            is_active=True,
            is_default=True,
        ))
    db.flush()
    return True


def list_room_types(db: Session, hospital_id: int) -> list[RoomType]:
    seed_room_types(db, hospital_id)
    return (
        db.query(RoomType)
        .filter(RoomType.hospital_id == hospital_id, RoomType.is_active.is_(True))
        .order_by(RoomType.is_default.desc(), RoomType.label)
        .all()
    )


def room_type_labels(db: Session, hospital_id: int) -> dict[str, str]:
    return {row.key: row.label for row in list_room_types(db, hospital_id)}


def ensure_room_type(db: Session, hospital_id: int, raw: str) -> str:
    """Return the catalog key, creating the type when it is new."""
    key = room_type_key(raw)
    seed_room_types(db, hospital_id)
    row = (
        db.query(RoomType)
        .filter(RoomType.hospital_id == hospital_id, RoomType.key == key)
        .first()
    )
    if row:
        if not row.is_active:
            row.is_active = True
            db.flush()
        return key
    db.add(RoomType(
        hospital_id=hospital_id,
        key=key,
        label=_label_for(raw, key),
        is_active=True,
        is_default=False,
    ))
    db.flush()
    return key

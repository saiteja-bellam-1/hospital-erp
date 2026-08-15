"""Canonical system-module catalog + license sync helpers.

Module Management lists rows from ``system_modules``. New modules added in
app upgrades (e.g. physiotherapy) must be inserted for existing customer DBs.
License upload alone used to only *disable* unlicensed modules — it never
created missing rows — so a renewed .lic with a new feature could not make
that module appear. These helpers heal that gap.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session

# (module_name, display_name, default_enabled, is_always_enabled)
CANONICAL_SYSTEM_MODULES: Sequence[Tuple[str, str, bool, bool]] = (
    ("outpatient", "Outpatient", True, False),
    ("inpatient", "Inpatient", False, False),
    ("lab", "Laboratory", False, False),
    ("pharmacy", "Pharmacy", False, False),
    ("physiotherapy", "Physiotherapy", False, False),
    ("ehr", "Electronic Health Records", True, False),
    ("billing", "Billing", True, True),
    ("admin", "Administration", True, True),
)


def ensure_system_modules(
    db: Session,
    *,
    licensed_features: Optional[Iterable[str]] = None,
) -> Set[str]:
    """Insert any missing canonical ``SystemModule`` rows.

    When ``licensed_features`` is provided, newly inserted toggleable modules
    that appear in that set are created already enabled (so an upgrade +
    already-installed license with physiotherapy does not leave physio stuck
    Disabled until a re-upload).

    Returns the set of module_name values that were newly inserted.
    """
    from app.models.system import SystemModule

    licensed_set = set(licensed_features) if licensed_features is not None else None
    created: Set[str] = set()

    for mod_name, display, default_enabled, always_on in CANONICAL_SYSTEM_MODULES:
        existing = (
            db.query(SystemModule)
            .filter(SystemModule.module_name == mod_name)
            .first()
        )
        if not existing:
            if always_on:
                enabled = True
            elif licensed_set is not None:
                enabled = mod_name in licensed_set
            else:
                enabled = default_enabled
            db.add(
                SystemModule(
                    module_name=mod_name,
                    display_name=display,
                    description=f"{display} management",
                    is_enabled=enabled,
                    is_always_enabled=always_on,
                )
            )
            created.add(mod_name)
        else:
            if existing.is_always_enabled != always_on:
                existing.is_always_enabled = always_on
                if always_on:
                    existing.is_enabled = True

    return created


def sync_modules_with_license(
    db: Session,
    licensed_features: list,
    *,
    previous_features: Optional[Iterable[str]] = None,
) -> None:
    """Align ``system_modules`` with a license ``features`` list.

    - Ensures every canonical module row exists (upgrade heal).
    - Disables toggleable modules not in the license.
    - Enables modules that are newly covered by this license (present in
      ``licensed_features`` but not in ``previous_features``), including rows
      that were just inserted. Does **not** re-enable modules an admin left
      disabled when the feature was already licensed before.
    """
    from app.models.system import SystemModule

    if not licensed_features:
        # Still heal missing catalog rows so Module Management stays complete.
        ensure_system_modules(db, licensed_features=None)
        db.commit()
        return

    licensed_set = set(licensed_features)
    previous_set = set(previous_features or [])

    created = ensure_system_modules(db, licensed_features=licensed_set)
    db.flush()

    newly_licensed = licensed_set - previous_set

    for module in db.query(SystemModule).all():
        if module.is_always_enabled:
            module.is_enabled = True
            continue
        if module.module_name not in licensed_set:
            if module.is_enabled:
                module.is_enabled = False
            continue
        # Licensed: enable when newly licensed or just created for this feature.
        if module.module_name in newly_licensed or module.module_name in created:
            module.is_enabled = True

    db.commit()

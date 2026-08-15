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


PENDING_LICENSE_MODULE_SYNC = ".pending_license_module_sync"


def queue_post_upgrade_module_sync(exe_dir: str) -> str:
    """Write a flag so the next heal pass force-syncs modules with the license.

    Software Update / Inno upgrade-in-place replaces the .exe but writes no
    install_seed.json. Without this one-shot, Module Management never picks up
    new catalog rows (e.g. physiotherapy) on upgraded customer DBs.
    """
    import os

    flag = os.path.join(exe_dir, "data", PENDING_LICENSE_MODULE_SYNC)
    os.makedirs(os.path.dirname(flag), exist_ok=True)
    with open(flag, "w", encoding="utf-8") as f:
        f.write("1\n")
    return flag


def heal_system_modules(exe_dir: Optional[str] = None) -> None:
    """Insert missing SystemModule rows; on post-upgrade flag, sync with license.

    Safe to call from the frozen launcher (before uvicorn) and from FastAPI
    startup. Idempotent. Never raises — failures are printed and swallowed so
    boot can continue.
    """
    import os

    try:
        from config.database import SessionLocal, reinitialize_engine, create_tables
        from app.models.system import SystemModule  # noqa: F401
        from app.services.license_service import get_current_license
        from app.utils.paths import get_data_dir

        reinitialize_engine()
        create_tables()

        # Launcher passes the .exe directory; FastAPI startup uses the resolved
        # data dir (backend/ in source mode, <exe>/data when bundled).
        data_dir = os.path.join(exe_dir, "data") if exe_dir else get_data_dir()
        flag = os.path.join(data_dir, PENDING_LICENSE_MODULE_SYNC)
        pending = os.path.isfile(flag)

        db = SessionLocal()
        try:
            lic = get_current_license(db)
            features = list(lic.features or []) if lic else []
            if pending and features:
                # previous_features=[] → every licensed feature counts as newly
                # covered: create missing rows AND enable them (heals physio
                # after Software Update when the license already included it).
                sync_modules_with_license(db, features, previous_features=[])
                print("  Post-upgrade module catalog synced with license features")
            else:
                created = ensure_system_modules(
                    db, licensed_features=features if features else None
                )
                db.commit()
                for mod_name in sorted(created):
                    print(f"  Added module: {mod_name}")
            if pending:
                try:
                    os.remove(flag)
                except OSError as e:
                    print(f"Warning: could not clear module sync flag: {e}")
        finally:
            db.close()
    except Exception as e:
        print(f"Warning: Module catalog heal failed: {e}")

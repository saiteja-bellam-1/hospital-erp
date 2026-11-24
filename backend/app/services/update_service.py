"""In-app self-update for the bundled KT HEALTH ERP Windows application.

Flow: list signed manifests published on GitHub Releases -> the operator
picks a version -> download that installer -> verify its SHA-256 -> keep a
database copy of the version being left -> launch the installer elevated and
exit so it can replace the locked .exe.

Rolling back to an older build also restores the database copy saved when
that version was last left. Schema migrations only move forward, so an older
program must not open a database a newer build has already migrated.

Security: each manifest is Ed25519-signed with KT's private key and verified
here against the public key embedded in app/licensing/crypto.py — the same
trust root as .lic licenses. A tampered manifest or installer is rejected
before anything is executed.

Only the `apply` step is Windows + bundled-only; check/download work anywhere
so the flow can be exercised in dev.
"""
import os
import re
import sys
import json
import hashlib
import shutil
import sqlite3
import threading
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

from app.version import APP_VERSION
from app.licensing.crypto import verify_signed_manifest
from app.utils.paths import get_data_dir, get_state_dir, is_bundled
from app.utils.config import load_config, save_config, run_backup

logger = logging.getLogger(__name__)

# GitHub repo that hosts the Releases (manifest.json + installer .exe assets).
# Releases must be publicly downloadable. Override per-deployment with the
# "update_repo" key in config.json.
DEFAULT_UPDATE_REPO = "saiteja-bellam-1/KTH-releases"

MANIFEST_ASSET = "manifest.json"
HTTP_TIMEOUT = 20  # seconds for the manifest fetch
DOWNLOAD_CHUNK = 256 * 1024
MAX_RELEASES = 20
MAX_SNAPSHOTS = 3
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Module-level download progress, polled by GET /api/system/update/status.
_download_state = {
    "state": "idle",          # idle | downloading | verifying | ready | error
    "bytes": 0,
    "total": 0,
    "version": None,
    "error": None,
    "installer_path": None,
    "relation": None,         # newer | older | current
    "snapshot_taken_at": None,
    "source": None,           # download | offline
}
_download_lock = threading.Lock()

# Verified release catalog. installer URLs stay here — they are not returned
# to the browser. The client names a version; the server looks it up.
_catalog = {
    "by_version": {},
    "error": None,
    "warning": None,
    "checked_at": None,
}
_catalog_lock = threading.Lock()


# ----------------------------------------------------------------------------
#   version helpers
# ----------------------------------------------------------------------------

def get_current_version() -> str:
    return APP_VERSION


def canonical_version(v: str) -> str:
    """'v1.2.3' / '1.2.3-beta' -> '1.2.3'. Rejects anything that is not x.y.z."""
    text = (v or "").strip().lstrip("vV")
    text = text.split("-")[0].split("+")[0]
    if not _VERSION_RE.match(text):
        raise ValueError(f"Unsupported version: {v}")
    return text


def _parse_semver(v: str):
    """Turn '1.2.3' (or 'v1.2.3') into a comparable tuple. Non-numeric
    components degrade to 0 so a malformed string never crashes the compare."""
    v = (v or "").strip().lstrip("vV")
    # drop any pre-release / build suffix
    v = v.split("-")[0].split("+")[0]
    parts = []
    for chunk in v.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def version_relation(candidate: str, current: str) -> str:
    """'newer', 'older', or 'current'."""
    left = _parse_semver(candidate)
    right = _parse_semver(current)
    if left > right:
        return "newer"
    if left < right:
        return "older"
    return "current"


def _is_newer(candidate: str, current: str) -> bool:
    return version_relation(candidate, current) == "newer"


def plan_apply(current: str, target: str, restore_requested: bool, snapshot_versions) -> dict:
    """Decide whether installing `target` keeps the live database or restores
    a saved copy. Older targets always restore; without a saved copy they are
    refused, because the live database may already contain newer migrations.
    """
    current_v = canonical_version(current)
    target_v = canonical_version(target)
    have = {canonical_version(v) for v in (snapshot_versions or [])}
    relation = version_relation(target_v, current_v)
    if relation == "current":
        raise ValueError(f"Version {target_v} is already installed")
    if relation == "older":
        if target_v not in have:
            raise ValueError(
                f"No saved database from version {target_v}. "
                "Installing an older program without that copy can make the "
                "hospital data unreadable. A copy is saved automatically each "
                "time an update leaves a version."
            )
        return {"relation": "older", "restore_snapshot": True, "version": target_v}
    if restore_requested and target_v not in have:
        raise ValueError(f"No saved database from version {target_v}")
    return {
        "relation": "newer",
        "restore_snapshot": bool(restore_requested) and target_v in have,
        "version": target_v,
    }


# ----------------------------------------------------------------------------
#   config helpers
# ----------------------------------------------------------------------------

def _update_repo() -> str:
    return (load_config().get("update_repo") or DEFAULT_UPDATE_REPO).strip("/ ")


def _manifest_url() -> str:
    # GitHub's stable "latest release asset" redirect — no API call, no rate limit.
    cfg = load_config()
    if cfg.get("update_manifest_url"):
        return cfg["update_manifest_url"]
    return f"https://github.com/{_update_repo()}/releases/latest/download/{MANIFEST_ASSET}"


def _installer_url(asset_name: str) -> str:
    return f"https://github.com/{_update_repo()}/releases/latest/download/{asset_name}"


def _allowed_download_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return host == "github.com" or host.endswith(".githubusercontent.com")


def _updates_dir() -> str:
    d = os.path.join(get_data_dir(), "updates")
    os.makedirs(d, exist_ok=True)
    return d


def _rollbacks_dir() -> str:
    d = os.path.join(get_state_dir(), "rollbacks")
    os.makedirs(d, exist_ok=True)
    return d


def _sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(DOWNLOAD_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _github_headers() -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "KTHEALTHERP-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ----------------------------------------------------------------------------
#   database snapshots (one per version left behind)
# ----------------------------------------------------------------------------

def list_snapshot_meta(root: str | None = None) -> dict:
    """version -> {version, taken_at, bytes} for each saved database copy."""
    root = root or _rollbacks_dir()
    found = {}
    if not os.path.isdir(root):
        return found
    for name in os.listdir(root):
        folder = os.path.join(root, name)
        meta_path = os.path.join(folder, "meta.json")
        db_path = os.path.join(folder, "kthealth_erp.db")
        if not os.path.isdir(folder) or not os.path.isfile(db_path):
            continue
        meta = {"version": name, "taken_at": None, "bytes": os.path.getsize(db_path)}
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    meta["taken_at"] = loaded.get("taken_at")
                    meta["version"] = loaded.get("version") or name
            except Exception:
                pass
        try:
            key = canonical_version(meta["version"])
        except ValueError:
            continue
        found[key] = meta
    return found


def snapshot_database(src_db: str, dest_dir: str, version: str) -> dict:
    """Online-safe copy of `src_db` into dest_dir/<version>/kthealth_erp.db.

    Writes to a partial file and replaces the previous copy only after the
    new file passes an integrity check, so a failed snapshot cannot destroy
    the last good one.
    """
    if not os.path.isfile(src_db):
        raise RuntimeError("Database file not found")
    version = canonical_version(version)
    folder = os.path.join(dest_dir, version)
    os.makedirs(folder, exist_ok=True)
    dest_db = os.path.join(folder, "kthealth_erp.db")
    partial = dest_db + ".partial"
    src = sqlite3.connect(src_db)
    try:
        dst = sqlite3.connect(partial)
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    finally:
        src.close()

    from app.utils.backup_verify import verify_backup_artifact
    verify = verify_backup_artifact(partial, full_check=True, source_db_path=src_db)
    if not verify.get("ok"):
        for path in (partial, partial + ".verified.json"):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        raise RuntimeError(
            "Database copy failed verification: "
            + (verify.get("error") or verify.get("integrity") or "unknown error")
        )
    os.replace(partial, dest_db)
    partial_sidecar = partial + ".verified.json"
    if os.path.isfile(partial_sidecar):
        try:
            os.remove(partial_sidecar)
        except OSError:
            pass
    meta = {
        "version": version,
        "taken_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "bytes": os.path.getsize(dest_db),
    }
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return meta


def prune_snapshots(root: str, keep: int = MAX_SNAPSHOTS, protect=None) -> list:
    """Delete the oldest snapshot folders beyond `keep`. Versions in `protect`
    are always kept, even when that leaves more than `keep` copies.
    """
    protect = set(protect or [])
    if not os.path.isdir(root):
        return []
    items = []
    for name in os.listdir(root):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        taken = ""
        meta_path = os.path.join(folder, "meta.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    taken = str(json.load(f).get("taken_at") or "")
            except Exception:
                taken = ""
        items.append((taken, name, folder))
    items.sort(reverse=True)
    removed = []
    kept = 0
    for _taken, name, folder in items:
        if name in protect or kept < keep:
            kept += 1
            continue
        shutil.rmtree(folder, ignore_errors=True)
        removed.append(name)
    return removed


def restore_database_file(snapshot_db: str, dest_db: str) -> None:
    """Replace `dest_db` with the contents of a verified snapshot.

    The caller closes other connections first. SQLite's backup API writes
    through the destination connection, then a checkpoint drops any WAL so
    the next process opens the restored file.
    """
    if not os.path.isfile(snapshot_db):
        raise RuntimeError("Saved database copy not found")
    from app.utils.backup_verify import verify_backup_artifact
    verify = verify_backup_artifact(snapshot_db, full_check=True)
    if not verify.get("ok"):
        raise RuntimeError(
            "Saved database copy failed verification: "
            + (verify.get("error") or verify.get("integrity") or "unknown error")
        )
    parent = os.path.dirname(dest_db)
    if parent:
        os.makedirs(parent, exist_ok=True)
    src = sqlite3.connect(snapshot_db)
    try:
        dst = sqlite3.connect(dest_db)
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    finally:
        src.close()
    for suffix in ("-wal", "-shm"):
        sidecar = dest_db + suffix
        if os.path.isfile(sidecar):
            try:
                os.remove(sidecar)
            except OSError:
                pass


PENDING_RESTORE = "pending.json"


def write_pending_restore(from_version: str, target_version: str) -> None:
    """Remember a database swap that the next launch must undo if this
    executable is still the version that started it.

    The installer can only replace the program after this process exits, so
    a swap that is followed by a failed install has to be reversible from
    the copy saved under `from_version`.
    """
    folder = _rollbacks_dir()
    path = os.path.join(folder, PENDING_RESTORE)
    payload = {
        "from_version": canonical_version(from_version),
        "target_version": canonical_version(target_version),
        "written_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    partial = path + ".partial"
    with open(partial, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(partial, path)


def clear_pending_restore() -> None:
    path = os.path.join(_rollbacks_dir(), PENDING_RESTORE)
    try:
        os.remove(path)
    except OSError:
        pass


def consume_pending_version_change() -> str | None:
    """Undo a database swap whose installer never replaced this executable.

    Called at startup, before schema migrations. When this build is still the
    one that started the change, the saved copy of that version is put back
    and the marker is removed. When a different build is running, the change
    stuck, so the marker is only cleared.
    """
    folder = os.path.join(get_state_dir(), "rollbacks")
    path = os.path.join(folder, PENDING_RESTORE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        return f"Could not read the pending version change: {e}"

    from_version = str((payload or {}).get("from_version") or "")
    try:
        still_here = canonical_version(from_version) == canonical_version(get_current_version())
    except ValueError:
        still_here = False

    if not still_here:
        try:
            os.remove(path)
        except OSError:
            pass
        return (
            f"Version change from {from_version or '?'} completed; "
            "the pending database marker was cleared."
        )

    from app.utils.paths import get_db_path
    snapshot_db = os.path.join(folder, canonical_version(from_version), "kthealth_erp.db")
    try:
        restore_database_file(snapshot_db, get_db_path())
    except Exception as e:
        # Leave the marker so the next start tries again.
        return (
            f"Version {payload.get('target_version')} did not replace the program, "
            f"and the database could not be put back: {e}"
        )
    try:
        os.remove(path)
    except OSError:
        pass
    return (
        f"Version {payload.get('target_version')} did not replace the program. "
        f"The database was put back to the copy saved for {from_version}."
    )


def _snapshot_running_version() -> dict | None:
    """Save the live database under the version that is running now."""
    from app.utils.paths import get_db_path
    db_path = get_db_path()
    if not os.path.isfile(db_path):
        logger.warning("No database file at %s — version snapshot skipped", db_path)
        return None
    meta = snapshot_database(db_path, _rollbacks_dir(), get_current_version())
    logger.info("Saved database snapshot for version %s", meta["version"])
    return meta


# Which background backups _pause_backups stopped, so a cancelled install
# resumes only those and leaves a stopped backup stopped.
_backup_pause = {"mirror": False, "snapshot": False}


def _pause_backups() -> None:
    from app.utils.config import get_mirror_status, stop_mirror_backup
    from app.utils.config import get_snapshot_status, stop_snapshot_backup

    mirror = bool(get_mirror_status().get("running"))
    scheduled = bool(get_snapshot_status().get("running"))
    _backup_pause["mirror"] = mirror
    _backup_pause["snapshot"] = scheduled
    if mirror:
        stop_mirror_backup()
    if scheduled:
        stop_snapshot_backup()


def _resume_backups() -> None:
    from app.middleware.maintenance import disable_maintenance_mode
    from app.utils.config import start_mirror_backup, start_snapshot_backup, load_config

    disable_maintenance_mode()
    mirror = _backup_pause.get("mirror")
    scheduled = _backup_pause.get("snapshot")
    _backup_pause["mirror"] = False
    _backup_pause["snapshot"] = False
    if mirror:
        try:
            start_mirror_backup(interval_seconds=60)
        except Exception:
            logger.warning("Could not resume mirror backup after update")
    if scheduled:
        try:
            minutes = load_config().get("snapshot_interval_minutes", 30)
            start_snapshot_backup(interval_minutes=minutes)
        except Exception:
            logger.warning("Could not resume scheduled backup after update")


def _begin_version_change(version: str) -> None:
    """Stop other writes so the saved database matches the file we leave behind.

    Held until the installer has started (the process then exits) or until
    `_abort_version_change` puts things back.
    """
    from app.middleware.maintenance import enable_maintenance_mode
    import time
    enable_maintenance_mode(f"Installing version {version}")
    try:
        _pause_backups()
        time.sleep(1)
    except Exception:
        _resume_backups()
        raise


def _replace_live_database(version: str) -> None:
    """Put the saved database for `version` in place of the live one.

    Does not run migrations: the process that next opens the file is the
    build being installed, and it applies its own schema steps. Caller has
    already paused writes and closed nothing yet — this disposes the pool.
    """
    from config.database import reinitialize_engine
    from app.utils.paths import get_db_path

    version = canonical_version(version)
    snapshot_db = os.path.join(_rollbacks_dir(), version, "kthealth_erp.db")
    if not os.path.isfile(snapshot_db):
        raise RuntimeError(f"No saved database from version {version}")
    reinitialize_engine()
    try:
        restore_database_file(snapshot_db, get_db_path())
    except Exception:
        reinitialize_engine()
        raise
    reinitialize_engine()
    logger.info("Live database replaced with the copy saved for version %s", version)


def _abort_version_change(swapped: bool, current_version: str) -> None:
    """Resume the running app. If the live file was already replaced, put
    the copy saved at the start of this attempt back first."""
    if not swapped:
        clear_pending_restore()
        _resume_backups()
        return
    try:
        _undo_database_swap(current_version)
    except Exception as undo_error:
        logger.error("Could not restore the database after a cancelled update: %s", undo_error)
        _resume_backups()
        raise RuntimeError(
            "The update did not start, and the database could not be put back "
            f"to version {current_version}. Restore it from Backup Management. "
            f"({undo_error})"
        ) from undo_error
    clear_pending_restore()


def _undo_database_swap(version: str) -> None:
    """Put the just-saved copy of `version` back. Used when the installer
    never actually started after a rollback had already swapped the file."""
    from config.database import reinitialize_engine
    from app.utils.paths import get_db_path

    version = canonical_version(version)
    snapshot_db = os.path.join(_rollbacks_dir(), version, "kthealth_erp.db")
    try:
        reinitialize_engine()
        restore_database_file(snapshot_db, get_db_path())
        reinitialize_engine()
    finally:
        _resume_backups()


# ----------------------------------------------------------------------------
#   release catalog
# ----------------------------------------------------------------------------

def _entry_from_manifest(manifest: dict, installer_url: str, tag, prerelease: bool) -> dict:
    version = canonical_version(str(manifest.get("latest_version") or ""))
    asset = manifest.get("installer_asset")
    expected_sha = (manifest.get("installer_sha256") or "").lower()
    if not asset or not expected_sha:
        raise ValueError(f"Manifest for {version} is missing installer_asset / installer_sha256")
    if installer_url and not _allowed_download_url(installer_url):
        raise ValueError(f"Installer URL for {version} is not on the release host")
    return {
        "version": version,
        "tag": tag,
        "release_notes": manifest.get("release_notes") or "",
        "released_at": manifest.get("released_at"),
        "mandatory": bool(manifest.get("mandatory")),
        "prerelease": bool(prerelease),
        "installer_asset": asset,
        "installer_sha256": expected_sha,
        "installer_size": int(manifest.get("installer_size") or 0),
        "installer_url": installer_url,
    }


def dedupe_entries(entries: list) -> list:
    """One entry per version. When two tags claim the same version, keep the
    later released_at."""
    by_version = {}
    for entry in entries:
        try:
            key = canonical_version(entry.get("version"))
        except ValueError:
            continue
        prev = by_version.get(key)
        if prev is None or (entry.get("released_at") or "") > (prev.get("released_at") or ""):
            by_version[key] = entry
    return list(by_version.values())


def newest_installable(entries: list, current: str, include_prerelease: bool = False):
    """Highest version newer than `current`. Pre-releases are skipped unless
    asked for — they stay selectable, but they are not the default update."""
    best = None
    for entry in entries:
        if entry.get("prerelease") and not include_prerelease:
            continue
        try:
            if version_relation(entry["version"], current) != "newer":
                continue
        except Exception:
            continue
        if best is None or version_relation(entry["version"], best["version"]) == "newer":
            best = entry
    return best


def public_release(entry: dict, current: str, snapshots: dict) -> dict:
    """Fields the browser is allowed to see. Download URLs and hashes stay
    on the server."""
    version = canonical_version(entry["version"])
    snap = snapshots.get(version) or {}
    return {
        "version": version,
        "released_at": entry.get("released_at"),
        "release_notes": entry.get("release_notes") or "",
        "mandatory": bool(entry.get("mandatory")),
        "prerelease": bool(entry.get("prerelease")),
        "installer_size": entry.get("installer_size") or 0,
        "relation": version_relation(version, current),
        "snapshot_available": bool(snap),
        "snapshot_taken_at": snap.get("taken_at"),
    }


def _fetch_manifest_text(url: str) -> dict:
    resp = requests.get(
        url, timeout=HTTP_TIMEOUT, headers={"User-Agent": "KTHEALTHERP-updater"},
    )
    resp.raise_for_status()
    return verify_signed_manifest(resp.text)


def _release_entry(rel: dict, manifest_url: str):
    manifest = _fetch_manifest_text(manifest_url)
    version_hint = str(manifest.get("latest_version") or "")
    asset_name = manifest.get("installer_asset")
    installer_asset = next(
        (a for a in (rel.get("assets") or []) if a.get("name") == asset_name),
        None,
    )
    if not installer_asset or not installer_asset.get("browser_download_url"):
        raise ValueError(f"Release {version_hint} has no installer asset {asset_name}")
    return _entry_from_manifest(
        manifest,
        installer_asset["browser_download_url"],
        rel.get("tag_name"),
        bool(rel.get("prerelease")),
    )


def _fetch_github_releases() -> list:
    url = f"https://api.github.com/repos/{_update_repo()}/releases?per_page={MAX_RELEASES}"
    resp = requests.get(url, headers=_github_headers(), timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        raise ValueError("Update server returned an unexpected release list")
    jobs = []
    for rel in payload:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        manifest_asset = next(
            (a for a in (rel.get("assets") or []) if a.get("name") == MANIFEST_ASSET),
            None,
        )
        if not manifest_asset or not manifest_asset.get("browser_download_url"):
            continue
        jobs.append((rel, manifest_asset["browser_download_url"]))

    entries = []
    if not jobs:
        return entries
    workers = min(8, len(jobs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_release_entry, rel, manifest_url) for rel, manifest_url in jobs]
        for fut in futures:
            try:
                entries.append(fut.result())
            except Exception as e:
                logger.warning("Skipping a release that could not be verified: %s", e)
    return dedupe_entries(entries)


def _fallback_latest_entry() -> dict:
    manifest = _fetch_manifest_text(_manifest_url())
    asset = manifest.get("installer_asset")
    return _entry_from_manifest(
        manifest,
        _installer_url(asset) if asset else "",
        None,
        False,
    )


def refresh_catalog() -> dict:
    """Fetch and verify the published releases. A custom update_manifest_url
    stays a single-version channel. If the releases API is unreachable, fall
    back to the latest manifest so 'check for updates' still works.
    """
    cfg = load_config()
    warning = None
    error = None
    entries = []
    if cfg.get("update_manifest_url"):
        try:
            entries = [_fallback_latest_entry()]
        except requests.RequestException as e:
            error = f"Could not reach the update server: {e}"
        except ValueError as e:
            error = str(e)
        except Exception as e:
            error = f"Update check failed: {e}"
    else:
        try:
            entries = _fetch_github_releases()
        except requests.RequestException as e:
            warning = f"Could not list published versions ({e})."
        except Exception as e:
            warning = f"Could not list published versions ({e})."
        if not entries:
            try:
                entries = [_fallback_latest_entry()]
            except requests.RequestException as e:
                error = f"Could not reach the update server: {e}"
            except ValueError as e:
                error = str(e)
            except Exception as e:
                error = f"Update check failed: {e}"
            else:
                if warning:
                    warning += " Showing the latest version only."
        else:
            warning = None

    by_version = {}
    for entry in dedupe_entries(entries):
        by_version[entry["version"]] = entry
    checked_at = datetime.datetime.now().isoformat(timespec="seconds")
    with _catalog_lock:
        _catalog["by_version"] = by_version
        _catalog["error"] = error
        _catalog["warning"] = warning
        _catalog["checked_at"] = checked_at
    return {"by_version": by_version, "error": error, "warning": warning, "checked_at": checked_at}


def _catalog_snapshot() -> dict:
    with _catalog_lock:
        return {
            "by_version": dict(_catalog["by_version"]),
            "error": _catalog["error"],
            "warning": _catalog["warning"],
            "checked_at": _catalog["checked_at"],
        }


# ----------------------------------------------------------------------------
#   check
# ----------------------------------------------------------------------------

def check_for_update() -> dict:
    """Fetch + verify signed manifests and compare them with the installed
    version. Returns a status dict; never raises for an offline box — the
    error is in the payload.
    """
    current = get_current_version()
    loaded = refresh_catalog()
    entries = list(loaded["by_version"].values())
    latest = newest_installable(entries, current)
    # When nothing is newer, still report the highest published version so the
    # page can say which build is current without calling it an update.
    display = latest
    if display is None and entries:
        display = max(entries, key=lambda e: _parse_semver(e["version"]))
    newer = []
    for entry in entries:
        try:
            if version_relation(entry["version"], current) == "newer" and not entry.get("prerelease"):
                newer.append(entry)
        except ValueError:
            continue
    try:
        snapshots = list_snapshot_meta()
    except Exception as e:
        logger.warning("Could not read saved version databases: %s", e)
        snapshots = {}
    releases = [
        public_release(entry, current, snapshots)
        for entry in sorted(entries, key=lambda e: _parse_semver(e["version"]), reverse=True)
    ]
    result = {
        "current_version": current,
        "latest_version": display.get("version") if display else None,
        "update_available": bool(newer),
        "mandatory": any(bool(entry.get("mandatory")) for entry in newer),
        "release_notes": (display.get("release_notes") if display else "") or "",
        "released_at": display.get("released_at") if display else None,
        "checked_at": loaded["checked_at"],
        "error": loaded["error"],
        "catalog_warning": loaded["warning"],
        "releases": releases,
    }
    if not loaded["error"]:
        try:
            cfg = load_config()
            cfg["last_update_check"] = result["checked_at"]
            save_config(cfg)
        except Exception:
            pass
    return result


# ----------------------------------------------------------------------------
#   download
# ----------------------------------------------------------------------------

def get_download_status() -> dict:
    with _download_lock:
        return dict(_download_state)


def _set_state(**kw):
    with _download_lock:
        _download_state.update(kw)


def _lookup_version(version: str | None) -> tuple[dict | None, str | None]:
    """Return (entry, error). A missing catalog is refreshed once."""
    current = get_current_version()
    catalog = _catalog_snapshot()
    if version:
        try:
            key = canonical_version(version)
        except ValueError as e:
            return None, str(e)
        entry = catalog["by_version"].get(key)
        if entry is None:
            catalog = refresh_catalog()
            entry = catalog["by_version"].get(key)
        if entry is None:
            if catalog.get("error"):
                return None, catalog["error"]
            return None, f"Version {key} is not in the signed release list"
        if version_relation(entry["version"], current) == "current":
            return None, f"Version {key} is already installed"
        return entry, None

    if not catalog["by_version"]:
        catalog = refresh_catalog()
    if catalog.get("error") and not catalog["by_version"]:
        return None, catalog["error"]
    entry = newest_installable(list(catalog["by_version"].values()), current)
    if entry is None:
        return None, "No update available"
    return entry, None


def start_download(version: str | None = None) -> dict:
    """Kick off a background download of one signed installer.

    `version` selects a published release (newer or older). Omit it to
    download the newest stable release newer than the one installed.
    Progress is polled via get_download_status().
    """
    with _download_lock:
        if _download_state["state"] == "downloading":
            return {"started": False, "reason": "A download is already in progress"}

    entry, reason = _lookup_version(version)
    if entry is None:
        return {"started": False, "reason": reason}

    current = get_current_version()
    relation = version_relation(entry["version"], current)
    snap = list_snapshot_meta().get(entry["version"])
    if relation == "older" and not snap:
        return {
            "started": False,
            "reason": (
                f"No saved database from version {entry['version']}. "
                "Rollback needs the copy taken when that version was last left."
            ),
        }
    with _download_lock:
        if _download_state["state"] == "downloading":
            return {"started": False, "reason": "A download is already in progress"}
        _download_state.update(
            state="downloading", bytes=0, total=entry.get("installer_size") or 0,
            version=entry["version"], error=None, installer_path=None,
            relation=relation, snapshot_taken_at=(snap or {}).get("taken_at"),
            source="download",
        )

    t = threading.Thread(target=_download_worker, args=(entry,),
                         daemon=True, name="update-download")
    t.start()
    return {"started": True, "version": entry["version"], "relation": relation}


def _download_worker(entry: dict):
    try:
        asset = entry.get("installer_asset")
        expected_sha = (entry.get("installer_sha256") or "").lower()
        url = entry.get("installer_url") or (_installer_url(asset) if asset else "")
        if not asset or not expected_sha or not url:
            raise ValueError("Release is missing the installer name, hash, or URL")
        if not _allowed_download_url(url):
            raise ValueError("Installer URL is not on the release host")

        updates_dir = _updates_dir()
        # Clear any stale staged installers before downloading a fresh one.
        # Snapshot folders live elsewhere and are not touched.
        for name in os.listdir(updates_dir):
            try:
                os.remove(os.path.join(updates_dir, name))
            except Exception:
                pass

        dest = os.path.join(updates_dir, os.path.basename(asset))
        with requests.get(url, stream=True, timeout=HTTP_TIMEOUT,
                          headers={"User-Agent": "KTHEALTHERP-updater"}) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or entry.get("installer_size") or 0)
            _set_state(total=total)
            written = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK):
                    if not chunk:
                        continue
                    f.write(chunk)
                    written += len(chunk)
                    _set_state(bytes=written)

        _set_state(state="verifying")
        actual_sha = _sha256_of(dest)
        if actual_sha.lower() != expected_sha:
            try:
                os.remove(dest)
            except Exception:
                pass
            raise ValueError("Downloaded installer failed its SHA-256 check — discarded")

        _set_state(state="ready", installer_path=dest)
        logger.info("Update %s downloaded and verified: %s", entry.get("version"), dest)
    except Exception as e:
        logger.error("Update download failed: %s", e)
        _set_state(state="error", error=str(e))


# ----------------------------------------------------------------------------
#   offline upload path
# ----------------------------------------------------------------------------

def stage_offline_update(installer_bytes: bytes, manifest_text: str) -> dict:
    """Verify + stage an installer the operator supplied manually (air-gapped
    sites). The manifest is signature-verified and the installer SHA-256 must
    match it — identical trust checks to the online path.

    An older installer is accepted only when a database copy from that version
    was saved on a previous update. Applying it restores that copy.
    """
    manifest = verify_signed_manifest(manifest_text)  # raises ValueError if bad

    asset = manifest.get("installer_asset")
    expected_sha = (manifest.get("installer_sha256") or "").lower()
    latest = str(manifest.get("latest_version") or "").strip()
    if not asset or not expected_sha or not latest:
        raise ValueError("Manifest is missing required fields")

    version = canonical_version(latest)
    actual_sha = hashlib.sha256(installer_bytes).hexdigest().lower()
    if actual_sha != expected_sha:
        raise ValueError("Uploaded installer does not match the manifest (SHA-256 mismatch)")

    relation = version_relation(version, get_current_version())
    if relation == "current":
        raise ValueError(
            f"Uploaded build ({version}) is the same as the installed version"
        )
    snap = list_snapshot_meta().get(version)
    if relation == "older" and not snap:
        raise ValueError(
            f"Uploaded build ({version}) is older than the installed version "
            f"({get_current_version()}), and no database copy from {version} "
            "is saved. Rollback needs that copy."
        )

    updates_dir = _updates_dir()
    for name in os.listdir(updates_dir):
        try:
            os.remove(os.path.join(updates_dir, name))
        except Exception:
            pass
    dest = os.path.join(updates_dir, os.path.basename(asset))
    with open(dest, "wb") as f:
        f.write(installer_bytes)

    _set_state(
        state="ready", version=version, bytes=len(installer_bytes),
        total=len(installer_bytes), error=None, installer_path=dest,
        relation=relation, snapshot_taken_at=(snap or {}).get("taken_at"),
        source="offline",
    )
    logger.info("Offline update %s staged and verified: %s", version, dest)
    return {"version": version, "relation": relation, "installer_path": dest}


# ----------------------------------------------------------------------------
#   apply
# ----------------------------------------------------------------------------

def apply_update(restore_snapshot: bool = False) -> dict:
    """Launch the staged installer elevated, then exit so it can replace the
    locked .exe. Windows + bundled only.

    The live database is copied under the current version first, so this
    version can be restored later. Writes are paused before that copy.
    When the staged build is older — or the operator asked to restore a
    newer version's saved database — that copy replaces the live file
    before the installer is launched. If the elevation prompt is declined,
    the replacement is undone and the running app is left as it was.
    """
    if sys.platform != "win32" or not is_bundled():
        raise RuntimeError(
            "Self-update can only be applied from the installed Windows application."
        )

    with _download_lock:
        state = _download_state["state"]
        installer_path = _download_state["installer_path"]
        staged_version = _download_state.get("version")
    if state != "ready" or not installer_path or not os.path.isfile(installer_path):
        raise RuntimeError("No verified update is staged — download an update first.")
    if not staged_version:
        raise RuntimeError("Staged update has no version.")

    try:
        plan = plan_apply(
            get_current_version(),
            staged_version,
            restore_snapshot,
            list_snapshot_meta().keys(),
        )
    except ValueError as e:
        raise RuntimeError(str(e)) from e

    current = canonical_version(get_current_version())
    # Pause writes before the copy, so the saved file matches the database
    # the new process will open (or the one we put back if this is cancelled).
    _begin_version_change(plan["version"])
    swapped = False
    try:
        try:
            _snapshot_running_version()
        except Exception as e:
            raise RuntimeError(
                f"Could not save a database copy of version {current}, so the "
                f"update was not started. {e}"
            ) from e
        # The snapshot just written must survive pruning, and so must the copy
        # we are about to restore.
        protect = {current}
        if plan["restore_snapshot"]:
            protect.add(plan["version"])
        prune_snapshots(_rollbacks_dir(), keep=MAX_SNAPSHOTS, protect=protect)

        # Operator backup folders, while the live file is still the current one.
        try:
            run_backup()
        except Exception as e:
            logger.warning("Pre-update backup failed (continuing): %s", e)

        if plan["restore_snapshot"]:
            # Set before the copy. A failure halfway through has already
            # changed the live file, so the abort path must put it back.
            # The marker lets the next start undo the copy if this executable
            # is still running because the installer never replaced it.
            swapped = True
            write_pending_restore(current, plan["version"])
            _replace_live_database(plan["version"])

        import ctypes
        # ShellExecuteW with the "runas" verb raises the UAC prompt. subprocess
        # cannot launch an elevation-required exe (fails with error 740).
        SW_HIDE = 0
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", installer_path,
            "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART", None, SW_HIDE,
        )
    except Exception:
        _abort_version_change(swapped, current)
        raise

    # ShellExecuteW returns > 32 on success; <= 32 means failed / UAC cancelled.
    if int(rc) <= 32:
        logger.warning("Installer launch returned %s (UAC cancelled or failed)", rc)
        _abort_version_change(swapped, current)
        raise RuntimeError(
            "Update was not started — the elevation prompt was declined or failed. "
            "The application is unchanged."
        )

    logger.info(
        "Installer launched (rc=%s) for version %s (restore_snapshot=%s); "
        "scheduling process exit for handoff.",
        rc, plan["version"], plan["restore_snapshot"],
    )
    # Give the HTTP response time to reach the browser, then exit so the .exe
    # file lock releases and the installer can overwrite it. The installer's
    # PrepareToInstall step also polls for the lock as a backstop.
    threading.Timer(2.0, _exit_for_update).start()
    return {
        "applying": True,
        "version": plan["version"],
        "relation": plan["relation"],
        "restore_snapshot": plan["restore_snapshot"],
    }


def _exit_for_update():
    logger.info("Exiting for self-update handoff.")
    # Hard exit — releases the .exe lock immediately and deterministically.
    # A DB backup was already taken and there is no in-flight write here.
    os._exit(0)

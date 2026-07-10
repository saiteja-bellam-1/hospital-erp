"""In-app self-update for the bundled KT HEALTH ERP Windows application.

Flow: check a signed manifest published on GitHub Releases -> if a newer
version exists, download the installer -> verify its SHA-256 -> back up the DB
-> launch the installer elevated and exit so it can replace the locked .exe.

Security: the manifest is Ed25519-signed with KT's private key and verified
here against the public key embedded in app/licensing/crypto.py — the same
trust root as .lic licenses. A tampered manifest or installer is rejected
before anything is executed.

Only the `apply` step is Windows + bundled-only; check/download work anywhere
so the flow can be exercised in dev.
"""
import os
import sys
import json
import hashlib
import shutil
import threading
import datetime
import logging

import requests

from app.version import APP_VERSION
from app.licensing.crypto import verify_signed_manifest
from app.utils.paths import get_data_dir, is_bundled
from app.utils.config import load_config, save_config, run_backup

logger = logging.getLogger(__name__)

# GitHub repo that hosts the Releases (manifest.json + installer .exe assets).
# Releases must be publicly downloadable. Override per-deployment with the
# "update_repo" key in config.json.
DEFAULT_UPDATE_REPO = "saiteja-bellam-1/KTH-releases"

MANIFEST_ASSET = "manifest.json"
HTTP_TIMEOUT = 20  # seconds for the manifest fetch
DOWNLOAD_CHUNK = 256 * 1024

# Module-level download progress, polled by GET /api/system/update/status.
_download_state = {
    "state": "idle",          # idle | downloading | verifying | ready | error
    "bytes": 0,
    "total": 0,
    "version": None,
    "error": None,
    "installer_path": None,
}
_download_lock = threading.Lock()


# ----------------------------------------------------------------------------
#   version helpers
# ----------------------------------------------------------------------------

def get_current_version() -> str:
    return APP_VERSION


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


def _is_newer(candidate: str, current: str) -> bool:
    return _parse_semver(candidate) > _parse_semver(current)


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


def _updates_dir() -> str:
    d = os.path.join(get_data_dir(), "updates")
    os.makedirs(d, exist_ok=True)
    return d


def _sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(DOWNLOAD_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------
#   check
# ----------------------------------------------------------------------------

def check_for_update() -> dict:
    """Fetch + verify the signed manifest, compare versions. Returns a status
    dict; never raises for an offline box — the error is in the payload."""
    current = get_current_version()
    result = {
        "current_version": current,
        "latest_version": None,
        "update_available": False,
        "mandatory": False,
        "release_notes": "",
        "released_at": None,
        "checked_at": datetime.datetime.now().isoformat(),
        "error": None,
    }
    try:
        resp = requests.get(_manifest_url(), timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        manifest = verify_signed_manifest(resp.text)
    except requests.RequestException as e:
        result["error"] = f"Could not reach the update server: {e}"
        return result
    except ValueError as e:
        # Signature / format failure — do NOT treat as an update.
        result["error"] = str(e)
        return result
    except Exception as e:  # pragma: no cover - defensive
        result["error"] = f"Update check failed: {e}"
        return result

    latest = str(manifest.get("latest_version") or "").strip()
    result["latest_version"] = latest
    result["release_notes"] = manifest.get("release_notes") or ""
    result["released_at"] = manifest.get("released_at")
    result["mandatory"] = bool(manifest.get("mandatory"))
    result["update_available"] = bool(latest) and _is_newer(latest, current)
    # Stash the verified manifest so download/apply don't re-fetch + re-verify.
    result["_manifest"] = manifest

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


def start_download() -> dict:
    """Kick off a background download of the latest installer. Returns
    immediately; progress is polled via get_download_status()."""
    with _download_lock:
        if _download_state["state"] == "downloading":
            return {"started": False, "reason": "A download is already in progress"}

    check = check_for_update()
    if check.get("error"):
        return {"started": False, "reason": check["error"]}
    if not check.get("update_available"):
        return {"started": False, "reason": "No update available"}

    manifest = check["_manifest"]
    _set_state(state="downloading", bytes=0, total=0,
               version=manifest.get("latest_version"), error=None, installer_path=None)

    t = threading.Thread(target=_download_worker, args=(manifest,),
                         daemon=True, name="update-download")
    t.start()
    return {"started": True}


def _download_worker(manifest: dict):
    try:
        asset = manifest.get("installer_asset")
        expected_sha = (manifest.get("installer_sha256") or "").lower()
        if not asset or not expected_sha:
            raise ValueError("Manifest is missing installer_asset / installer_sha256")

        updates_dir = _updates_dir()
        # Clear any stale staged installers before downloading a fresh one.
        for name in os.listdir(updates_dir):
            try:
                os.remove(os.path.join(updates_dir, name))
            except Exception:
                pass

        dest = os.path.join(updates_dir, asset)
        with requests.get(_installer_url(asset), stream=True, timeout=HTTP_TIMEOUT) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or manifest.get("installer_size") or 0)
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
        logger.info("Update %s downloaded and verified: %s", manifest.get("latest_version"), dest)
    except Exception as e:
        logger.error("Update download failed: %s", e)
        _set_state(state="error", error=str(e))


# ----------------------------------------------------------------------------
#   offline upload path
# ----------------------------------------------------------------------------

def stage_offline_update(installer_bytes: bytes, manifest_text: str) -> dict:
    """Verify + stage an installer the operator supplied manually (air-gapped
    sites). The manifest is signature-verified and the installer SHA-256 must
    match it — identical trust checks to the online path."""
    manifest = verify_signed_manifest(manifest_text)  # raises ValueError if bad

    asset = manifest.get("installer_asset")
    expected_sha = (manifest.get("installer_sha256") or "").lower()
    latest = str(manifest.get("latest_version") or "").strip()
    if not asset or not expected_sha or not latest:
        raise ValueError("Manifest is missing required fields")

    actual_sha = hashlib.sha256(installer_bytes).hexdigest().lower()
    if actual_sha != expected_sha:
        raise ValueError("Uploaded installer does not match the manifest (SHA-256 mismatch)")

    if not _is_newer(latest, get_current_version()):
        raise ValueError(
            f"Uploaded build ({latest}) is not newer than the installed version "
            f"({get_current_version()})"
        )

    updates_dir = _updates_dir()
    for name in os.listdir(updates_dir):
        try:
            os.remove(os.path.join(updates_dir, name))
        except Exception:
            pass
    dest = os.path.join(updates_dir, asset)
    with open(dest, "wb") as f:
        f.write(installer_bytes)

    _set_state(state="ready", version=latest, bytes=len(installer_bytes),
               total=len(installer_bytes), error=None, installer_path=dest)
    logger.info("Offline update %s staged and verified: %s", latest, dest)
    return {"version": latest, "installer_path": dest}


# ----------------------------------------------------------------------------
#   apply
# ----------------------------------------------------------------------------

def apply_update() -> dict:
    """Launch the staged installer elevated, then exit so it can replace the
    locked .exe. Windows + bundled only. If the operator cancels the UAC
    prompt nothing is changed and the running app is left untouched."""
    if sys.platform != "win32" or not is_bundled():
        raise RuntimeError(
            "Self-update can only be applied from the installed Windows application."
        )

    with _download_lock:
        state = _download_state["state"]
        installer_path = _download_state["installer_path"]
    if state != "ready" or not installer_path or not os.path.isfile(installer_path):
        raise RuntimeError("No verified update is staged — download an update first.")

    # Safety net: a known-good DB backup before we hand control to the installer.
    try:
        run_backup()
    except Exception as e:
        logger.warning("Pre-update backup failed (continuing): %s", e)

    import ctypes
    # ShellExecuteW with the "runas" verb raises the UAC prompt. subprocess
    # cannot launch an elevation-required exe (fails with error 740).
    SW_HIDE = 0
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", installer_path,
        "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART", None, SW_HIDE,
    )
    # ShellExecuteW returns > 32 on success; <= 32 means failed / UAC cancelled.
    if int(rc) <= 32:
        logger.warning("Installer launch returned %s (UAC cancelled or failed)", rc)
        raise RuntimeError(
            "Update was not started — the elevation prompt was declined or failed. "
            "The application is unchanged."
        )

    logger.info("Installer launched (rc=%s); scheduling process exit for handoff.", rc)
    # Give the HTTP response time to reach the browser, then exit so the .exe
    # file lock releases and the installer can overwrite it. The installer's
    # PrepareToInstall step also polls for the lock as a backstop.
    threading.Timer(2.0, _exit_for_update).start()
    return {"applying": True, "version": _download_state.get("version")}


def _exit_for_update():
    logger.info("Exiting for self-update handoff.")
    # Hard exit — releases the .exe lock immediately and deterministically.
    # A DB backup was already taken and there is no in-flight write here.
    os._exit(0)

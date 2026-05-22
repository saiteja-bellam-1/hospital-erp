"""
Entry point for the bundled KT HEALTH ERP .exe.
Also works in dev mode for testing the bundled-like experience.

The server binds to 0.0.0.0 so it is accessible from any device
on the hospital's local network (e.g. http://192.168.1.100:8000).
"""
import sys
import os
import socket
import threading
import webbrowser
import time
import json
import datetime
import logging
from logging.handlers import RotatingFileHandler


# Embedded build version — single source of truth in app/version.py. Used by the
# upgrade-in-place detector below: when this differs from data/version.txt we
# know the operator just dropped in a newer .exe, so we can run any one-shot
# upgrade migrations and persist the new version. The guarded fallback covers
# the rare case where app/ is not yet importable at this point in startup.
try:
    from app.version import APP_VERSION
except Exception:  # pragma: no cover - defensive: keep launcher bootable
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from app.version import APP_VERSION
    except Exception:
        APP_VERSION = "1.1.0"


def setup_logging(exe_dir):
    """Mirror launcher + uvicorn output to data/logs/launcher.log so the
    Diagnostics endpoint and operator support can see what happened on
    boot. Rotates after 1MB, keeps 5 backups.
    """
    logs_dir = os.path.join(exe_dir, "data", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, "launcher.log")

    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Avoid duplicating handlers if main() runs twice
    if not any(getattr(h, "_kthealth_launcher", False) for h in root.handlers):
        handler._kthealth_launcher = True
        root.addHandler(handler)
    return log_file


def check_version_bump(exe_dir):
    """Detect upgrade-in-place by comparing APP_VERSION to data/version.txt.

    Returns one of:
      ("first_run", None)          -> data/version.txt did not exist
      ("upgrade", previous_version) -> versions differ
      ("same", current_version)     -> versions match
    Records the outcome in data/version.txt and data/.upgrade_history.json
    so an admin can see the upgrade trail.
    """
    version_file = os.path.join(exe_dir, "data", "version.txt")
    history_file = os.path.join(exe_dir, "data", ".upgrade_history.json")
    os.makedirs(os.path.dirname(version_file), exist_ok=True)

    previous = None
    if os.path.isfile(version_file):
        try:
            with open(version_file) as f:
                previous = f.read().strip()
        except Exception:
            previous = None

    if previous is None:
        outcome = "first_run"
    elif previous != APP_VERSION:
        outcome = "upgrade"
    else:
        outcome = "same"

    if outcome != "same":
        try:
            history = []
            if os.path.isfile(history_file):
                with open(history_file) as f:
                    history = json.load(f)
            history.append({
                "from": previous,
                "to": APP_VERSION,
                "outcome": outcome,
                "at": datetime.datetime.utcnow().isoformat() + "Z",
            })
            history = history[-50:]  # cap
            with open(history_file, "w") as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass

        try:
            with open(version_file, "w") as f:
                f.write(APP_VERSION)
        except Exception:
            pass

    return outcome, previous


def find_free_port(start=8000, end=8020):
    """Find a free port starting from `start`."""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


def get_local_ip():
    """Get the machine's LAN IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def open_browser(port, delay=1.5):
    """Open the default browser after a short delay."""
    def _open():
        time.sleep(delay)
        webbrowser.open(f"http://localhost:{port}")
    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


def _write_shortcut_status(exe_dir, status, **extras):
    """Persist shortcut creation outcome to data/.shortcut_status.json so the
    admin Diagnostics endpoint can surface it. Used to be a silent best-effort.
    """
    import json as _json
    import datetime as _dt
    payload = {
        "status": status,  # "created" | "skipped_existing" | "failed" | "skipped_no_desktop"
        "checked_at": _dt.datetime.utcnow().isoformat() + "Z",
        **extras,
    }
    try:
        data_dir = os.path.join(exe_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, ".shortcut_status.json"), "w") as f:
            _json.dump(payload, f, indent=2)
    except Exception:
        pass


def create_desktop_shortcut():
    """Create a desktop shortcut on first launch (Windows only).

    Result is recorded in data/.shortcut_status.json so the failure mode is
    visible in the Diagnostics page instead of being silently swallowed.
    """
    if not getattr(sys, 'frozen', False):
        return  # Only for .exe builds

    import platform
    if platform.system() != "Windows":
        return

    exe_path = sys.executable
    exe_dir = os.path.dirname(exe_path)

    # Check if shortcut was already created
    marker_file = os.path.join(exe_dir, "data", ".shortcut_created")
    if os.path.exists(marker_file):
        _write_shortcut_status(exe_dir, "skipped_existing")
        return

    # Get desktop path
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        _write_shortcut_status(exe_dir, "skipped_no_desktop", desktop=desktop)
        print(f"Note: Desktop folder not found at {desktop}; skipped shortcut creation")
        return

    shortcut_path = os.path.join(desktop, "KT HEALTH ERP.lnk")

    # Use PowerShell to create a .lnk shortcut
    icon_path = os.path.join(exe_dir, "assets", "icon.ico")
    if not os.path.exists(icon_path) and hasattr(sys, '_MEIPASS'):
        icon_path = os.path.join(sys._MEIPASS, "assets", "icon.ico")

    ps_script = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut("{shortcut_path}"); '
        f'$s.TargetPath = "{exe_path}"; '
        f'$s.WorkingDirectory = "{exe_dir}"; '
        f'$s.Description = "KT HEALTH ERP - Hospital Management System"; '
    )
    if os.path.exists(icon_path):
        ps_script += f'$s.IconLocation = "{icon_path}"; '
    ps_script += '$s.Save()'

    try:
        import subprocess
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0 or not os.path.exists(shortcut_path):
            _write_shortcut_status(
                exe_dir, "failed",
                desktop=desktop,
                shortcut_path=shortcut_path,
                stderr=(proc.stderr or "").strip()[:500],
                returncode=proc.returncode,
            )
            print(f"Note: Could not create desktop shortcut (returncode {proc.returncode}): {proc.stderr.strip()[:200]}")
            return

        # Mark as done so we don't create it again
        os.makedirs(os.path.dirname(marker_file), exist_ok=True)
        with open(marker_file, "w") as f:
            f.write("1")

        _write_shortcut_status(exe_dir, "created", shortcut_path=shortcut_path)
        print("Desktop shortcut created: KT HEALTH ERP")
    except Exception as e:
        _write_shortcut_status(exe_dir, "failed", error=str(e))
        print(f"Note: Could not create desktop shortcut: {e}")


# --- Console / windowless-mode handling -------------------------------------
# The bundled exe is built console=False (GUI subsystem), so it runs windowless
# by default and we pipe stdout/stderr into a log file. Launched with --debug it
# attaches a real console so an operator can watch logs live. None of this
# applies in dev mode (python launcher.py) — there a normal terminal exists.

_instance_mutex = None  # kept alive for the process lifetime so the lock holds


def _is_debug_requested():
    """True when the operator wants a visible log console."""
    if any(a in ("--debug", "-d") for a in sys.argv[1:]):
        return True
    return os.environ.get("KTHEALTH_DEBUG", "").strip() in ("1", "true", "True")


def _enable_debug_console():
    """Attach a real console to this GUI-subsystem process so logs are visible.

    Attaches to the parent terminal when launched from cmd/PowerShell; otherwise
    allocates a fresh console window. Caller redirects to a log file if this
    leaves stdout unusable. No-op outside frozen Windows.
    """
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ATTACH_PARENT_PROCESS = -1
        if not kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            kernel32.AllocConsole()
        sys.stdout = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
        sys.stderr = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
        try:
            sys.stdin = open("CONIN$", "r", encoding="utf-8")
        except Exception:
            pass
    except Exception:
        pass  # caller falls back to log-file redirection


def _redirect_output_to_logfile(exe_dir):
    """Windowless mode: a console=False exe has no usable stdout/stderr. Point
    them at data/logs/server.log so print() AND uvicorn output are captured.
    uvicorn resolves ext://sys.stdout at uvicorn.run() time, after this swap.
    Rotates once when the file grows past ~2 MB."""
    logs_dir = os.path.join(exe_dir, "data", "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, "server.log")
        if os.path.isfile(log_path) and os.path.getsize(log_path) > 2_000_000:
            os.replace(log_path, log_path + ".old")
        f = open(log_path, "a", buffering=1, encoding="utf-8", errors="replace")
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass


def _acquire_single_instance(exe_dir):
    """Return True if this is the only instance. If the app is already running,
    open the browser to it and return False so the caller can exit. Returns True
    (does not block startup) outside frozen Windows or on any failure."""
    global _instance_mutex
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        _instance_mutex = kernel32.CreateMutexW(None, False, "KTHEALTHERP_SingleInstance")
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            port = 8000
            try:
                with open(os.path.join(exe_dir, "data", ".runtime_port")) as f:
                    port = int(f.read().strip())
            except Exception:
                pass
            try:
                webbrowser.open(f"http://localhost:{port}")
            except Exception:
                pass
            return False
        return True
    except Exception:
        return True


def main():
    debug_mode = _is_debug_requested()

    # If running as PyInstaller bundle, set up paths before importing app
    if getattr(sys, 'frozen', False):
        # Change working directory to where the .exe lives
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)

        # Ensure data directory exists
        data_dir = os.path.join(exe_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(os.path.join(data_dir, "uploads"), exist_ok=True)

        # Decide console mode BEFORE anything prints — a console=False exe has
        # no usable stdout until we attach a console or redirect to a log file.
        if debug_mode:
            _enable_debug_console()
        if not debug_mode or sys.stdout is None:
            _redirect_output_to_logfile(exe_dir)

        # Single-instance guard: if the app is already running, focus it and exit.
        if not _acquire_single_instance(exe_dir):
            return

        # Copy icon to accessible location (outside the temp _MEIPASS dir)
        assets_dir = os.path.join(exe_dir, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        if hasattr(sys, '_MEIPASS'):
            bundled_icon = os.path.join(sys._MEIPASS, "assets", "icon.ico")
            local_icon = os.path.join(assets_dir, "icon.ico")
            if os.path.exists(bundled_icon) and not os.path.exists(local_icon):
                import shutil
                shutil.copy2(bundled_icon, local_icon)

        # Capture launcher + uvicorn output to data/logs/launcher.log
        log_file = setup_logging(exe_dir)
        log = logging.getLogger("launcher")

        print(f"KT HEALTH ERP - Bundled Mode (v{APP_VERSION})")
        print(f"Data directory: {data_dir}")
        print(f"Log file:       {log_file}")
        log.info("Launcher boot, version=%s", APP_VERSION)

        # Detect upgrade-in-place. The schema-migrations runner in main.py
        # handles the actual data migration; we just record the version bump
        # so the Diagnostics page can show "you upgraded from 1.0.0 to 1.1.0"
        # and any one-shot upgrade hooks (added later) can branch on it.
        outcome, previous = check_version_bump(exe_dir)
        if outcome == "first_run":
            log.info("First run — no previous version recorded")
        elif outcome == "upgrade":
            print(f"Upgrade detected: {previous} -> {APP_VERSION}")
            log.warning("Upgrade detected from %s to %s", previous, APP_VERSION)
        else:
            log.info("Same version as previous launch")

        # Create desktop shortcut on first launch
        create_desktop_shortcut()

        # Apply installer-collected seed (hospital, admin, license, backups)
        # if the wizard left one behind. Idempotent: a no-op when no seed
        # file exists. Failures are logged + recorded; we let the app boot
        # so the React fallback wizard can still take over.
        try:
            from app.services.bootstrap_from_seed import consume_seed_if_present
            seed_status = consume_seed_if_present(exe_dir)
            if seed_status is None:
                log.info("No installer seed file present")
            elif seed_status.get("applied"):
                log.info("Installer seed applied successfully")
            else:
                log.error("Installer seed apply failed: %s", seed_status.get("error"))
        except Exception:
            log.exception("Bootstrap from seed raised; continuing to fallback wizard")
    else:
        # Dev mode: change to backend directory
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(backend_dir)
        print("KT HEALTH ERP - Development Mode")

    # Find a free port
    port = find_free_port()
    local_ip = get_local_ip()

    # Record the live port so a duplicate launch can focus this instance.
    if getattr(sys, 'frozen', False):
        try:
            runtime_port_file = os.path.join(
                os.path.dirname(sys.executable), "data", ".runtime_port")
            with open(runtime_port_file, "w") as f:
                f.write(str(port))
        except Exception:
            pass

    print()
    print("=" * 50)
    print("  KT HEALTH ERP Server")
    print("=" * 50)
    print(f"  Local:     http://localhost:{port}")
    print(f"  Network:   http://{local_ip}:{port}")
    print()
    print("  Other computers on the network can access")
    print(f"  the app at: http://{local_ip}:{port}")
    print("=" * 50)
    print()

    # Open browser on this machine
    open_browser(port)

    # Import and run the app
    import uvicorn
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            reload=False,
            log_level="debug" if debug_mode else "info",
        )
    except KeyboardInterrupt:
        print("\nShutting down KT HEALTH ERP...")


if __name__ == "__main__":
    main()

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


def create_desktop_shortcut():
    """Create a desktop shortcut on first launch (Windows only)."""
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
        return

    try:
        # Get desktop path
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            return

        shortcut_path = os.path.join(desktop, "KT HEALTH ERP.lnk")

        # Use PowerShell to create a .lnk shortcut
        icon_path = os.path.join(exe_dir, "assets", "icon.ico")
        if not os.path.exists(icon_path):
            # Try inside the bundled _MEIPASS directory
            if hasattr(sys, '_MEIPASS'):
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

        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, timeout=10,
        )

        # Mark as done so we don't create it again
        os.makedirs(os.path.dirname(marker_file), exist_ok=True)
        with open(marker_file, "w") as f:
            f.write("1")

        print("Desktop shortcut created: KT HEALTH ERP")
    except Exception as e:
        print(f"Note: Could not create desktop shortcut: {e}")


def main():
    # If running as PyInstaller bundle, set up paths before importing app
    if getattr(sys, 'frozen', False):
        # Change working directory to where the .exe lives
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)

        # Ensure data directory exists
        data_dir = os.path.join(exe_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(os.path.join(data_dir, "uploads"), exist_ok=True)

        # Copy icon to accessible location (outside the temp _MEIPASS dir)
        assets_dir = os.path.join(exe_dir, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        if hasattr(sys, '_MEIPASS'):
            bundled_icon = os.path.join(sys._MEIPASS, "assets", "icon.ico")
            local_icon = os.path.join(assets_dir, "icon.ico")
            if os.path.exists(bundled_icon) and not os.path.exists(local_icon):
                import shutil
                shutil.copy2(bundled_icon, local_icon)

        print(f"KT HEALTH ERP - Bundled Mode")
        print(f"Data directory: {data_dir}")

        # Create desktop shortcut on first launch
        create_desktop_shortcut()
    else:
        # Dev mode: change to backend directory
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(backend_dir)
        print("KT HEALTH ERP - Development Mode")

    # Find a free port
    port = find_free_port()
    local_ip = get_local_ip()

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
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\nShutting down KT HEALTH ERP...")


if __name__ == "__main__":
    main()

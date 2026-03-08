"""
Entry point for the bundled Hospital ERP .exe.
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
        # Connect to an external address to determine the local IP
        # (doesn't actually send any data)
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

        print(f"Hospital ERP - Bundled Mode")
        print(f"Data directory: {data_dir}")
    else:
        # Dev mode: change to backend directory
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(backend_dir)
        print("Hospital ERP - Development Mode")

    # Find a free port
    port = find_free_port()
    local_ip = get_local_ip()

    print()
    print("=" * 50)
    print("  Hospital ERP Server")
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
            host="0.0.0.0",      # Bind to all interfaces for LAN access
            port=port,
            reload=False,         # reload is incompatible with PyInstaller
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\nShutting down Hospital ERP...")


if __name__ == "__main__":
    main()

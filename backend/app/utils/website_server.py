"""Public introduction site, on its own port.

The hospital program login stays on the ERP port (3000 while developing).
This server only serves frontend/website.
"""
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

WEBSITE_PORT = 8080
DEV_ERP_PORT = 3000

_started = False


def erp_origin(host_header: str, erp_port: int) -> str:
    """Build the ERP origin from the browser's host, keeping the login port."""
    host = (host_header or "localhost").strip()
    if host.startswith("["):
        hostname = host.split("]")[0] + "]"
    elif host.count(":") == 1:
        hostname = host.rsplit(":", 1)[0]
    else:
        hostname = host or "localhost"
    return f"http://{hostname}:{erp_port}"


def render_login_links(html: str, host_header: str, erp_port: int) -> str:
    return html.replace("__ERP_ORIGIN__", erp_origin(host_header, erp_port))


def website_directory() -> str:
    from app.utils.paths import get_base_dir, get_bundle_dir, is_bundled

    if is_bundled():
        return os.path.join(get_bundle_dir(), "website")
    return os.path.join(os.path.dirname(get_base_dir()), "frontend", "website")


def erp_login_port() -> int:
    """Dev UI is the React server on 3000. The packaged app serves login itself."""
    from app.utils.paths import get_data_dir, is_bundled

    if not is_bundled():
        return DEV_ERP_PORT
    runtime = os.path.join(get_data_dir(), ".runtime_port")
    try:
        with open(runtime, encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return 8000


def _should_autostart() -> bool:
    if os.environ.get("DISABLE_WEBSITE") == "1":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return "pytest" not in sys.modules


class _WebsiteHandler(SimpleHTTPRequestHandler):
    erp_port = DEV_ERP_PORT

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def list_directory(self, path):
        self.send_error(404, "Not found")
        return None

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send_index()
            return
        super().do_GET()

    def _send_index(self):
        index_path = os.path.join(self.directory, "index.html")
        try:
            with open(index_path, encoding="utf-8") as handle:
                html = handle.read()
        except OSError:
            self.send_error(404, "Not found")
            return
        body = render_login_links(html, self.headers.get("Host", ""), self.erp_port).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


class _ReuseServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_website_server(erp_port: int | None = None, port: int | None = None) -> bool:
    """Listen in a daemon thread. Safe to call again; a second bind is skipped."""
    global _started
    if _started:
        return True
    if not _should_autostart() and os.environ.get("WEBSITE_FORCE") != "1":
        return False

    directory = website_directory()
    if not os.path.isfile(os.path.join(directory, "index.html")):
        print(f"Website not started — missing {os.path.join(directory, 'index.html')}")
        return False

    login_port = DEV_ERP_PORT if erp_port is None else erp_port
    listen_port = WEBSITE_PORT if port is None else port

    class BoundHandler(_WebsiteHandler):
        pass

    BoundHandler.erp_port = login_port

    def handler(*args, **kwargs):
        return BoundHandler(*args, directory=directory, **kwargs)

    try:
        httpd = _ReuseServer(("0.0.0.0", listen_port), handler)
    except OSError as exc:
        print(f"Website port {listen_port} is already in use ({exc})")
        return False

    threading.Thread(target=httpd.serve_forever, name="website", daemon=True).start()
    _started = True
    print(f"Website:    http://localhost:{listen_port}")
    print(f"ERP login:  http://localhost:{login_port}/login")
    return True

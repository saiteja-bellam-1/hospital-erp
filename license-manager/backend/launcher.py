"""Entry point for License Manager .exe"""
import sys
import os
import webbrowser
import threading
import time


def main():
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    port = 9000

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{port}")
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()

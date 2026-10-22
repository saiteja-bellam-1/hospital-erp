#!/usr/bin/env python3
"""Host the introduction site without starting the hospital API.

ERP login stays on port 3000. This site listens on port 8080.
"""
import os
import sys
import time

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, BACKEND)

os.environ["WEBSITE_FORCE"] = "1"

from app.utils.website_server import DEV_ERP_PORT, WEBSITE_PORT, start_website_server


def main():
    erp_port = int(os.environ.get("ERP_PORT", str(DEV_ERP_PORT)))
    site_port = int(os.environ.get("WEBSITE_PORT", str(WEBSITE_PORT)))
    if not start_website_server(erp_port, site_port):
        sys.exit(1)
    print("Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nWebsite stopped")


if __name__ == "__main__":
    main()

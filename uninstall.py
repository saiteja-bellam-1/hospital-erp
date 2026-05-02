#!/usr/bin/env python3
"""
KT HEALTH ERP — source-install uninstaller.

Cleanly removes the local development environment created by
install_and_setup.py:

  - backend/venv/
  - frontend/node_modules/
  - backend/build/, backend/dist/, build_logs/
  - frontend/build/

By default, customer DATA (DB, uploads, config.json) is PRESERVED. Pass
--purge-data to also wipe:

  - backend/kthealth_erp.db (and -journal/-wal/-shm sidecars)
  - backend/data/ (when present — bundled-mode persistent dir)
  - backend/uploads/
  - backend/config.json

The script asks for confirmation before each major step; pass --yes to
skip all prompts (e.g. for CI / scripted teardown).

This script is for source installs only. To uninstall the Windows .exe
distribution, use Apps & Features (the Inno Setup installer registers a
proper uninstaller there).
"""

import argparse
import os
import shutil
import sys


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"  [auto-yes] {question}")
        return True
    answer = input(f"  {question} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def remove_path(path: str, label: str, assume_yes: bool) -> None:
    if not os.path.exists(path):
        print(f"  - {label}: not present, skipping")
        return
    if not confirm(f"Delete {label} at {path}?", assume_yes):
        print(f"  - {label}: skipped")
        return
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        print(f"  - {label}: removed")
    except Exception as e:
        print(f"  - {label}: FAILED — {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Uninstall a source install of KT HEALTH ERP")
    parser.add_argument("--purge-data", action="store_true",
                        help="Also delete the customer database, uploads, and config")
    parser.add_argument("--yes", action="store_true",
                        help="Skip all confirmation prompts")
    args = parser.parse_args()

    print("KT HEALTH ERP — Source Uninstaller")
    print("=" * 50)
    if args.purge_data:
        print("WARNING: --purge-data will delete the customer database.")
    else:
        print("Customer data (DB, uploads, config) will be PRESERVED.")
        print("Re-run with --purge-data to wipe customer data too.")
    print()

    if not confirm("Proceed?", args.yes):
        print("Aborted.")
        return 1

    backend = os.path.join(PROJECT_DIR, "backend")
    frontend = os.path.join(PROJECT_DIR, "frontend")

    print("\nRemoving build artifacts and dependencies...")
    remove_path(os.path.join(backend, "venv"),         "Backend virtualenv",  args.yes)
    remove_path(os.path.join(frontend, "node_modules"), "Frontend node_modules", args.yes)
    remove_path(os.path.join(backend, "build"),        "PyInstaller build/",   args.yes)
    remove_path(os.path.join(backend, "dist"),         "PyInstaller dist/",    args.yes)
    remove_path(os.path.join(frontend, "build"),       "Frontend build/",      args.yes)
    remove_path(os.path.join(PROJECT_DIR, "build_logs"), "build_logs/",        args.yes)

    if args.purge_data:
        print("\nWiping customer data (--purge-data)...")
        # SQLite files in the legacy backend/ location
        for fname in ("kthealth_erp.db", "kthealth_erp.db-journal",
                      "kthealth_erp.db-wal", "kthealth_erp.db-shm",
                      "hospital_erp.db", "config.json"):
            remove_path(os.path.join(backend, fname), fname, args.yes)
        # Bundled-mode persistent dir, if it leaked into the source tree
        remove_path(os.path.join(backend, "data"),    "backend/data/",    args.yes)
        remove_path(os.path.join(backend, "uploads"), "backend/uploads/", args.yes)
    else:
        print("\nCustomer data preserved.")

    print("\n" + "=" * 50)
    print("Uninstall complete.")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())

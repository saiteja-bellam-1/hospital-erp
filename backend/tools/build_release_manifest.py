#!/usr/bin/env python3
"""Build + sign a self-update manifest for KT HEALTH ERP.

Run this after `build_installer.bat` produces the installer .exe. It computes
the installer's SHA-256, assembles the manifest JSON, signs it with KT's
Ed25519 private key, and writes a `manifest.json` in the same 2-line
base64 format as a .lic file.

Publish BOTH files as assets on a GitHub Release so the app can fetch them
from `https://github.com/<owner>/<repo>/releases/latest/download/...`:
  - manifest.json
  - KTHEALTHERP_Setup_<version>.exe

Usage:
  python tools/build_release_manifest.py \
    --installer ../backend/dist/installer/KTHEALTHERP_Setup_1.2.0.exe \
    --version 1.2.0 \
    --notes-file release_notes.txt \
    --min-version 1.0.0

The script self-verifies the signed manifest against the public key embedded
in app/licensing/crypto.py, so a key mismatch is caught here — not in the field.
"""
import sys
import os
import argparse
import json
import hashlib
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.licensing.crypto import sign_manifest_data, verify_signed_manifest

DEFAULT_PRIVATE_KEY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "private_key.pem")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(256 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Build + sign a KT HEALTH ERP update manifest")
    ap.add_argument("--installer", required=True, help="Path to KTHEALTHERP_Setup_<ver>.exe")
    ap.add_argument("--version", required=True, help="Release version, e.g. 1.2.0")
    ap.add_argument("--min-version", default="1.0.0",
                    help="Oldest version that may upgrade directly to this one")
    ap.add_argument("--notes", default="", help="Release notes text")
    ap.add_argument("--notes-file", help="Read release notes from this file (overrides --notes)")
    ap.add_argument("--mandatory", action="store_true", help="Mark this update as required")
    ap.add_argument("--private-key", default=DEFAULT_PRIVATE_KEY,
                    help="Ed25519 private key PEM (default: tools/private_key.pem)")
    ap.add_argument("--output", help="Output manifest path (default: manifest.json next to installer)")
    args = ap.parse_args()

    if not os.path.isfile(args.installer):
        print(f"ERROR: installer not found: {args.installer}")
        sys.exit(1)
    if not os.path.isfile(args.private_key):
        print(f"ERROR: private key not found: {args.private_key}")
        sys.exit(1)

    notes = args.notes
    if args.notes_file:
        with open(args.notes_file, "r", encoding="utf-8") as f:
            notes = f.read().strip()

    manifest = {
        "latest_version": args.version,
        "min_supported_version": args.min_version,
        "installer_asset": os.path.basename(args.installer),
        "installer_sha256": sha256_of(args.installer),
        "installer_size": os.path.getsize(args.installer),
        "release_notes": notes,
        "released_at": datetime.date.today().isoformat(),
        "mandatory": bool(args.mandatory),
    }

    with open(args.private_key, "r", encoding="utf-8") as f:
        private_pem = f.read()

    signed = sign_manifest_data(manifest, private_pem)

    # Self-check: the deployed app verifies against the EMBEDDED public key.
    # If this fails, the private key does not match crypto.PUBLIC_KEY_PEM and
    # every client would reject the manifest — stop now.
    try:
        verify_signed_manifest(signed)
    except Exception as e:
        print(f"ERROR: signed manifest does not verify against the embedded "
              f"public key — wrong private key?\n  {e}")
        sys.exit(1)

    out = args.output or os.path.join(os.path.dirname(os.path.abspath(args.installer)), "manifest.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(signed)

    print("Manifest signed and verified OK.")
    print(json.dumps(manifest, indent=2))
    print(f"\nWritten: {out}")
    print(f"Installer: {args.installer}")
    print("\nNext: create a GitHub Release and attach BOTH files as assets:")
    print(f"  gh release create v{args.version} \\")
    print(f'    "{args.installer}" "{out}" \\')
    print(f'    --title "v{args.version}" --notes "{(notes or "").splitlines()[0] if notes else ""}"')


if __name__ == "__main__":
    main()

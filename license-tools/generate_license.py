#!/usr/bin/env python3
"""
License Generator Tool (Vendor-only) — Standalone, no backend dependency.
Generates signed .lic files for KT HEALTH ERP customers.

Usage:
  python generate_license.py generate-keys
  python generate_license.py create \
    --private-key keys/private_key.pem \
    --hospital-id K7X2M9 \
    --hospital-name "KT Hospital" \
    --plan standard \
    --max-users 50 \
    --days 365 \
    --features "outpatient,lab,ehr" \
    --output customer_license.lic
"""

import argparse
import json
import uuid
import os
import base64
from datetime import datetime, timedelta, UTC

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def generate_keypair():
    """Generate Ed25519 keypair. Returns (private_key_pem, public_key_pem)."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


def sign_license_data(license_data: dict, private_key_pem: str) -> str:
    """Sign license data with private key. Returns .lic file content."""
    private_key = serialization.load_pem_private_key(
        private_key_pem.strip().encode(), password=None
    )

    license_json = json.dumps(license_data, sort_keys=True, default=str)
    license_bytes = license_json.encode("utf-8")
    signature = private_key.sign(license_bytes)

    license_b64 = base64.b64encode(license_bytes).decode("utf-8")
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    return f"{license_b64}\n{signature_b64}"


def cmd_generate_keys(args):
    os.makedirs(args.output_dir, exist_ok=True)
    private_pem, public_pem = generate_keypair()

    private_path = os.path.join(args.output_dir, "private_key.pem")
    public_path = os.path.join(args.output_dir, "public_key.pem")

    with open(private_path, "w") as f:
        f.write(private_pem)
    with open(public_path, "w") as f:
        f.write(public_pem)

    print(f"Keys generated:")
    print(f"  Private key: {private_path} (KEEP SECRET!)")
    print(f"  Public key:  {public_path}")
    print(f"\nCopy the public key content into backend/app/licensing/crypto.py PUBLIC_KEY_PEM")
    print(f"\nPublic key:\n{public_pem}")


def cmd_create_license(args):
    with open(args.private_key, "r") as f:
        private_key_pem = f.read()

    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(days=args.days)

    features = args.features.split(",") if args.features else [
        "lab", "pharmacy", "inpatient", "outpatient", "ehr", "billing"
    ]

    license_data = {
        "license_id": str(uuid.uuid4()),
        "hospital_id": args.hospital_id,
        "hospital_name": args.hospital_name,
        "plan": args.plan,
        "max_users": args.max_users,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "features": features,
    }

    lic_content = sign_license_data(license_data, private_key_pem)

    with open(args.output, "w") as f:
        f.write(lic_content)

    print(f"License created: {args.output}")
    print(f"  License ID: {license_data['license_id']}")
    print(f"  Hospital: {args.hospital_name} (ID: {args.hospital_id})")
    print(f"  Plan: {args.plan}")
    print(f"  Max users: {args.max_users}")
    print(f"  Valid: {issued_at.strftime('%Y-%m-%d')} to {expires_at.strftime('%Y-%m-%d')} ({args.days} days)")
    print(f"  Features: {', '.join(features)}")

    # Append to audit log
    log_entry = {
        "license_id": license_data["license_id"],
        "hospital_id": args.hospital_id,
        "hospital_name": args.hospital_name,
        "plan": args.plan,
        "max_users": args.max_users,
        "features": features,
        "days": args.days,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "output_file": args.output,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "license_log.json")
    existing_log = []
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            try:
                existing_log = json.load(f)
            except json.JSONDecodeError:
                existing_log = []
    existing_log.append(log_entry)
    with open(log_path, "w") as f:
        json.dump(existing_log, f, indent=2, default=str)

    print(f"  Audit log updated: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="KT HEALTH ERP License Generator")
    subparsers = parser.add_subparsers(dest="command")

    # Generate keys
    gen_keys = subparsers.add_parser("generate-keys", help="Generate Ed25519 keypair")
    gen_keys.add_argument("--output-dir", default="keys", help="Output directory for keys")

    # Create license
    create = subparsers.add_parser("create", help="Create a signed license file")
    create.add_argument("--private-key", required=True, help="Path to private key PEM")
    create.add_argument("--hospital-id", type=str, required=True, help="6-char alphanumeric hospital code (from login page)")
    create.add_argument("--hospital-name", required=True)
    create.add_argument("--plan", default="standard", choices=["basic", "standard", "premium"])
    create.add_argument("--max-users", type=int, default=50)
    create.add_argument("--days", type=int, default=365, help="License validity in days")
    create.add_argument("--features", default=None, help="Comma-separated feature list")
    create.add_argument("--output", default="license.lic", help="Output .lic file path")

    args = parser.parse_args()

    if args.command == "generate-keys":
        cmd_generate_keys(args)
    elif args.command == "create":
        cmd_create_license(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

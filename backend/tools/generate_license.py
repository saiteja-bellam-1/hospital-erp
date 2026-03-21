#!/usr/bin/env python3
"""
License Generator for KT HEALTH ERP.

Usage:
  # Generate new keypair (one-time)
  python tools/generate_license.py --generate-keys

  # Generate a license file
  python tools/generate_license.py \
    --hospital-id ABC123 \
    --hospital-name "City Hospital" \
    --machine-id "A7F3-B2C1-9D4E" \
    --plan standard \
    --days 365 \
    --output city_hospital.lic

  # Get this machine's ID
  python tools/generate_license.py --show-machine-id
"""
import sys
import os
import argparse
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.licensing.crypto import generate_keypair, sign_license_data


def main():
    parser = argparse.ArgumentParser(description="KT HEALTH ERP License Generator")
    parser.add_argument("--generate-keys", action="store_true", help="Generate a new Ed25519 keypair")
    parser.add_argument("--show-machine-id", action="store_true", help="Show this machine's ID")
    parser.add_argument("--hospital-id", help="Hospital ID (6-char code)")
    parser.add_argument("--hospital-name", help="Hospital display name")
    parser.add_argument("--machine-id", help="Target machine ID (from customer's app)")
    parser.add_argument("--plan", default="standard", help="License plan (default: standard)")
    parser.add_argument("--max-users", type=int, default=50, help="Max users (default: 50)")
    parser.add_argument("--days", type=int, default=365, help="License validity in days (default: 365)")
    parser.add_argument("--features", nargs="*", default=["outpatient", "lab", "ehr", "admin"],
                        help="Enabled features/modules")
    parser.add_argument("--private-key", default="tools/private_key.pem", help="Path to private key PEM file")
    parser.add_argument("--output", "-o", help="Output .lic file path")

    args = parser.parse_args()

    if args.generate_keys:
        private_pem, public_pem = generate_keypair()
        with open("tools/private_key.pem", "w") as f:
            f.write(private_pem)
        with open("tools/public_key.pem", "w") as f:
            f.write(public_pem)
        print("Keypair generated:")
        print(f"  Private key: tools/private_key.pem")
        print(f"  Public key:  tools/public_key.pem")
        print()
        print("IMPORTANT: Copy the public key to app/licensing/crypto.py PUBLIC_KEY_PEM")
        print()
        print(public_pem)
        return

    if args.show_machine_id:
        from app.utils.machine_id import get_machine_id_full
        info = get_machine_id_full()
        print(f"Machine ID:  {info['machine_id']}")
        print(f"Hostname:    {info['hostname']}")
        print(f"MAC Address: {info['mac_address']}")
        print(f"OS:          {info['os']}")
        return

    # Generate license
    if not args.hospital_id or not args.hospital_name:
        parser.error("--hospital-id and --hospital-name are required")

    if not args.machine_id:
        parser.error("--machine-id is required (get it from the customer's app: /api/license/machine-id)")

    # Load private key
    if not os.path.exists(args.private_key):
        parser.error(f"Private key not found: {args.private_key}. Run --generate-keys first.")

    with open(args.private_key) as f:
        private_key_pem = f.read()

    import uuid
    now = datetime.utcnow()
    license_data = {
        "license_id": str(uuid.uuid4()),
        "hospital_id": args.hospital_id,
        "hospital_name": args.hospital_name,
        "machine_id": args.machine_id,
        "plan": args.plan,
        "max_users": args.max_users,
        "features": args.features,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(days=args.days)).isoformat(),
    }

    lic_content = sign_license_data(license_data, private_key_pem)

    output_path = args.output or f"{args.hospital_id}_{args.machine_id}.lic"
    with open(output_path, "w") as f:
        f.write(lic_content)

    print(f"License generated: {output_path}")
    print(f"  Hospital:   {args.hospital_name} ({args.hospital_id})")
    print(f"  Machine ID: {args.machine_id}")
    print(f"  Plan:       {args.plan}")
    print(f"  Max Users:  {args.max_users}")
    print(f"  Valid:      {args.days} days")
    print(f"  Expires:    {(now + timedelta(days=args.days)).strftime('%Y-%m-%d')}")
    print(f"  Features:   {', '.join(args.features)}")


if __name__ == "__main__":
    main()

import json
import base64
from datetime import datetime, date
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

# Public key for license verification (embedded in app)
# This gets replaced with the actual public key during initial setup
# Generate a keypair with: python tools/generate_license.py --generate-keys
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAxtFBGBmkF6F6hdfnaC4KSVD1wbJoO5G3dP6U0juNzfs=
-----END PUBLIC KEY-----"""


def load_public_key(pem_data: str = None) -> Ed25519PublicKey:
    pem = (pem_data or PUBLIC_KEY_PEM).strip().encode()
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Invalid key type: expected Ed25519 public key")
    return key


def verify_license_file(file_content: str, public_key_pem: str = None) -> dict:
    """Parse and verify a .lic file. Returns license data dict if valid."""
    try:
        lines = file_content.strip().split("\n")
        if len(lines) != 2:
            raise ValueError("Invalid license file format")

        license_data_b64 = lines[0]
        signature_b64 = lines[1]

        license_data_bytes = base64.b64decode(license_data_b64)
        signature = base64.b64decode(signature_b64)

        public_key = load_public_key(public_key_pem)
        # Verify signature — raises InvalidSignature if tampered
        public_key.verify(signature, license_data_bytes)

        license_data = json.loads(license_data_bytes.decode("utf-8"))
        return license_data

    except Exception as e:
        raise ValueError(f"License verification failed: {str(e)}")


def sign_license_data(license_data: dict, private_key_pem: str) -> str:
    """Sign license data with private key. Returns .lic file content."""
    private_key = serialization.load_pem_private_key(
        private_key_pem.strip().encode(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Invalid key type: expected Ed25519 private key")

    license_json = json.dumps(license_data, sort_keys=True, default=str)
    license_bytes = license_json.encode("utf-8")

    signature = private_key.sign(license_bytes)

    license_b64 = base64.b64encode(license_bytes).decode("utf-8")
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    return f"{license_b64}\n{signature_b64}"


def generate_keypair() -> tuple[str, str]:
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

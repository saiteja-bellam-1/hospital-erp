"""
Generate a unique Machine ID based on hardware identifiers.
Used for license binding — each license is tied to a specific machine.
"""
import hashlib
import uuid
import platform
import socket


def get_machine_id() -> str:
    """
    Generate a deterministic Machine ID for this computer.
    Based on: MAC address + hostname + OS.
    Returns a 12-char uppercase hex string like 'A7F3-B2C1-9D4E'.
    """
    # Get primary MAC address
    mac = uuid.getnode()
    mac_str = ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8))

    # Get hostname
    hostname = socket.gethostname()

    # Get OS info
    os_info = f"{platform.system()}-{platform.machine()}"

    # Combine and hash
    raw = f"{mac_str}|{hostname}|{os_info}"
    digest = hashlib.sha256(raw.encode()).hexdigest().upper()

    # Format as 3 groups of 4 chars
    machine_id = f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}"
    return machine_id


def get_machine_id_full() -> dict:
    """Get machine ID with debug details (for display purposes)."""
    mac = uuid.getnode()
    mac_str = ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8))

    return {
        "machine_id": get_machine_id(),
        "hostname": socket.gethostname(),
        "mac_address": mac_str,
        "os": f"{platform.system()} {platform.release()}",
    }

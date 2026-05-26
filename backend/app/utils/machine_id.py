"""
Generate a unique Machine ID for this computer. Used for license binding.

Computed once from MAC + hostname + OS, then frozen to
``<data_dir>/machine_id.txt``. Every subsequent call reads the file so the ID
cannot drift when the OS re-orders interfaces (Wi-Fi randomization, VPN,
sleep/wake, USB ethernet, AirDrop peers, etc.). The file travels with the
data folder, so moving the install to new hardware naturally requires a
rebind — which is the intended behaviour.
"""
import hashlib
import os
import uuid
import platform
import socket


def _compute_machine_id() -> str:
    mac = uuid.getnode()
    mac_str = ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8))
    hostname = socket.gethostname()
    os_info = f"{platform.system()}-{platform.machine()}"
    raw = f"{mac_str}|{hostname}|{os_info}"
    digest = hashlib.sha256(raw.encode()).hexdigest().upper()
    return f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}"


def _machine_id_file() -> str:
    # Imported lazily so this module stays import-light for dbcheck.exe.
    from app.utils.paths import get_data_dir
    return os.path.join(get_data_dir(), "machine_id.txt")


def get_machine_id() -> str:
    path = _machine_id_file()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = f.read().strip()
        if cached:
            return cached
    except FileNotFoundError:
        pass
    except OSError:
        # Unreadable file — fall through to recompute; do not overwrite.
        return _compute_machine_id()

    mid = _compute_machine_id()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(mid)
    except OSError:
        pass
    return mid


def get_machine_id_full() -> dict:
    mac = uuid.getnode()
    mac_str = ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8))
    return {
        "machine_id": get_machine_id(),
        "hostname": socket.gethostname(),
        "mac_address": mac_str,
        "os": f"{platform.system()} {platform.release()}",
    }

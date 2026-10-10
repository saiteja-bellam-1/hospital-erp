"""Short-lived PDFs that MSG91 fetches from this hospital's public address."""

import os
import secrets
import threading
import time

from app.utils.paths import get_data_dir

TTL_SECONDS = 15 * 60
_lock = threading.Lock()
_tokens: dict[str, tuple[str, float]] = {}


def _media_dir() -> str:
    path = os.path.join(get_data_dir(), "whatsapp_media")
    os.makedirs(path, exist_ok=True)
    return path


def publish(pdf_bytes: bytes) -> str:
    token = secrets.token_urlsafe(32)
    path = os.path.join(_media_dir(), f"{token}.pdf")
    with open(path, "wb") as handle:
        handle.write(pdf_bytes)
    with _lock:
        _tokens[token] = (path, time.time() + TTL_SECONDS)
    purge_expired()
    return token


def resolve(token: str) -> str | None:
    purge_expired()
    if not token or "/" in token or "\\" in token or token.startswith("."):
        return None
    with _lock:
        item = _tokens.get(token)
    if not item:
        return None
    path, expires_at = item
    if time.time() > expires_at or not os.path.isfile(path):
        discard(token)
        return None
    return path


def discard(token: str) -> None:
    with _lock:
        item = _tokens.pop(token, None)
    if not item:
        return
    path, _expires = item
    try:
        os.remove(path)
    except OSError:
        pass


def purge_expired() -> None:
    now = time.time()
    with _lock:
        expired = [token for token, (_path, exp) in _tokens.items() if exp <= now]
    for token in expired:
        discard(token)


def clear_all() -> None:
    """Test helper."""
    with _lock:
        tokens = list(_tokens)
    for token in tokens:
        discard(token)

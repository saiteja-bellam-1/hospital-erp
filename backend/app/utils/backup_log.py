"""
Dedicated backup error log.

Mirror / snapshot / Google Drive threads currently stash `last_error` in
memory or config.json. Those never reach `data/logs/*.log`, so an admin
opening the Backup page has no trail of what failed.

This module:
  - appends structured ERROR lines to `data/logs/backup.log`
  - mirrors them to stdout so windowless-mode `server.log` still captures them
  - reads backup.log plus launcher.log / server.log and returns backup-related
    error lines for the Backup page popup
"""
from __future__ import annotations

import datetime
import os
import re
from typing import Optional

_MAX_BYTES = 1_000_000
_BACKUP_HINT = re.compile(
    r"backup|gdrive|google drive|mirror backup|snapshot backup|restore database",
    re.IGNORECASE,
)
_ERROR_HINT = re.compile(
    r"\[error\]|\[critical\]|failed|error|exception|traceback",
    re.IGNORECASE,
)
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:,\d+)?)\s+"
    r"\[(?P<level>[A-Z]+)\]\s+"
    r"(?:(?P<source>[a-zA-Z0-9_-]+):\s*)?"
    r"(?P<message>.*)$"
)


def get_logs_dir() -> str:
    """Same folder the launcher / Diagnostics endpoint use: `{base}/data/logs`."""
    from app.utils.paths import get_base_dir
    path = os.path.join(get_base_dir(), "data", "logs")
    os.makedirs(path, exist_ok=True)
    return path


def backup_log_path() -> str:
    return os.path.join(get_logs_dir(), "backup.log")


def log_backup_error(source: str, message: str) -> None:
    """Append one ERROR line. Never raises — logging must not break backups."""
    text = " ".join(str(message).split())
    if not text:
        return
    src = (source or "backup").strip() or "backup"
    line = (
        f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"[ERROR] {src}: {text}\n"
    )
    try:
        path = backup_log_path()
        _rotate_if_needed(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    try:
        print(f"Backup error ({src}): {text}", flush=True)
    except Exception:
        pass


def read_backup_errors(max_entries: int = 100) -> dict:
    """Collect recent backup-related error lines from our log files."""
    max_entries = max(10, min(int(max_entries or 100), 500))
    logs_dir = get_logs_dir()
    collected: list[dict] = []

    backup_path = os.path.join(logs_dir, "backup.log")
    collected.extend(_read_file(backup_path, "backup", require_backup_hint=False))

    for name in ("launcher.log", "server.log"):
        collected.extend(
            _read_file(os.path.join(logs_dir, name), name.replace(".log", ""), require_backup_hint=True)
        )

    deduped = _dedupe(collected)
    deduped.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return {
        "path": backup_path,
        "count": len(deduped[:max_entries]),
        "errors": deduped[:max_entries],
    }


def _rotate_if_needed(path: str) -> None:
    try:
        if os.path.isfile(path) and os.path.getsize(path) > _MAX_BYTES:
            os.replace(path, path + ".old")
    except Exception:
        pass


def _read_file(path: str, file_label: str, require_backup_hint: bool) -> list[dict]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-2000:]
    except Exception:
        return []

    out = []
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if require_backup_hint and not _BACKUP_HINT.search(line):
            continue
        if not _ERROR_HINT.search(line):
            continue
        parsed = _parse_line(line, file_label)
        if parsed:
            out.append(parsed)
    return out


def _parse_line(line: str, file_label: str) -> Optional[dict]:
    m = _LINE_RE.match(line)
    if m:
        ts = m.group("ts").replace(",", ".")
        level = (m.group("level") or "ERROR").upper()
        source = m.group("source") or file_label
        message = (m.group("message") or "").strip()
        return {
            "timestamp": ts,
            "level": level,
            "source": source,
            "message": message,
            "file": file_label,
            "raw": line,
        }
    return {
        "timestamp": None,
        "level": "ERROR",
        "source": file_label,
        "message": line.strip(),
        "file": file_label,
        "raw": line,
    }


def _dedupe(entries: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for entry in entries:
        key = (entry.get("source") or "", (entry.get("message") or "")[:400])
        prev = seen.get(key)
        if prev is None or (entry.get("timestamp") or "") >= (prev.get("timestamp") or ""):
            seen[key] = entry
    return list(seen.values())

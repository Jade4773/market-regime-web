from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from werkzeug.security import generate_password_hash

from user_store import load_users


_LOCK = threading.Lock()
RUNTIME_USERS_FILE = Path(os.getenv("RUNTIME_USERS_FILE", "/tmp/market-regime-users-v2.json"))


def get_users() -> dict[str, Any]:
    with _LOCK:
        if not RUNTIME_USERS_FILE.exists():
            _save_unlocked(load_users())
        return _load_unlocked()


def authenticate(username: str, password: str) -> tuple[bool, dict[str, Any] | None]:
    from werkzeug.security import check_password_hash

    record = get_users().get(username.strip().lower())
    if not record or not record.get("enabled", True):
        return False, None
    return check_password_hash(record["password_hash"], password), record


def change_password(username: str, new_password: str, force_change: bool = False) -> None:
    with _LOCK:
        users = _load_unlocked()
        username = username.strip().lower()
        if username not in users:
            raise ValueError("사용자를 찾을 수 없습니다.")
        users[username]["password_hash"] = generate_password_hash(new_password)
        users[username]["force_change"] = force_change
        _save_unlocked(users)


def set_enabled(username: str, enabled: bool) -> None:
    with _LOCK:
        users = _load_unlocked()
        username = username.strip().lower()
        if username not in users:
            raise ValueError("사용자를 찾을 수 없습니다.")
        users[username]["enabled"] = enabled
        _save_unlocked(users)


def export_users() -> str:
    return json.dumps(get_users(), ensure_ascii=False, indent=2)


def _load_unlocked() -> dict[str, Any]:
    if not RUNTIME_USERS_FILE.exists():
        return {}
    with RUNTIME_USERS_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_unlocked(users: dict[str, Any]) -> None:
    RUNTIME_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = RUNTIME_USERS_FILE.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(users, handle, ensure_ascii=False, indent=2)
    temp_path.replace(RUNTIME_USERS_FILE)

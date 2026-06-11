from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_users(path: Path | None = None) -> dict[str, Any]:
    env_users = os.getenv("USERS_JSON")
    if env_users:
        return json.loads(env_users)

    if path is None:
        path = Path(os.getenv("USERS_FILE", "data/users.json"))

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_users(path: Path, users: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(users, handle, ensure_ascii=False, indent=2)

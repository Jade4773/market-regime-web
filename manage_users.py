from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

from user_store import load_users, save_users


load_dotenv()


def users_path() -> Path:
    return Path(os.getenv("USERS_FILE", "data/users.json"))


def add_user(username: str, password_arg: str | None = None) -> None:
    username = username.strip().lower()
    if not username:
        raise SystemExit("Username is required.")

    path = users_path()
    users = load_users(path)
    if len(users) >= 20 and username not in users:
        raise SystemExit("User limit reached: 20")

    if password_arg is None:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match.")
    else:
        password = password_arg
    if len(password) < 10:
        raise SystemExit("Use at least 10 characters.")

    users[username] = {
        "password_hash": generate_password_hash(password),
        "enabled": True,
    }
    save_users(path, users)
    print(f"Saved user: {username}")


def set_enabled(username: str, enabled: bool) -> None:
    path = users_path()
    users = load_users(path)
    username = username.strip().lower()
    if username not in users:
        raise SystemExit("User not found.")
    users[username]["enabled"] = enabled
    save_users(path, users)
    print(f"{'Enabled' if enabled else 'Disabled'} user: {username}")


def list_users() -> None:
    users = load_users(users_path())
    for username, record in sorted(users.items()):
        status = "enabled" if record.get("enabled", True) else "disabled"
        print(f"{username}: {status}")


def print_users_json() -> None:
    users = load_users(users_path())
    print(json.dumps(users, ensure_ascii=False, separators=(",", ":")))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("username")
    add.add_argument("--password")
    disable = sub.add_parser("disable")
    disable.add_argument("username")
    enable = sub.add_parser("enable")
    enable.add_argument("username")
    sub.add_parser("list")
    sub.add_parser("json")
    args = parser.parse_args()

    if args.command == "add":
        add_user(args.username, args.password)
    elif args.command == "disable":
        set_enabled(args.username, False)
    elif args.command == "enable":
        set_enabled(args.username, True)
    elif args.command == "list":
        list_users()
    elif args.command == "json":
        print_users_json()


if __name__ == "__main__":
    main()

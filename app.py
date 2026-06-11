from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from market_data import INDEXES, get_market_snapshot
from user_store import load_users


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["USERS_FILE"] = os.getenv("USERS_FILE", "data/users.json")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def authenticate(username: str, password: str) -> bool:
    users = load_users()
    record = users.get(username.strip().lower())
    if not record or not record.get("enabled", True):
        return False
    return check_password_hash(record["password_hash"], password)


@app.get("/login")
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.post("/login")
def login_post():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    if authenticate(username, password):
        session.clear()
        session["user"] = username.strip().lower()
        return redirect(request.args.get("next") or url_for("dashboard"))
    flash("아이디 또는 비밀번호가 맞지 않습니다.")
    return render_template("login.html"), 401


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    snapshot = get_market_snapshot()
    return render_template(
        "dashboard.html",
        indexes=INDEXES,
        snapshot=snapshot,
        user=session["user"],
        updated_at=datetime.now(timezone.utc),
    )


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)

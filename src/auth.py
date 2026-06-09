"""Authentication: JWT sessions, roles, OAuth (Google/Microsoft), audit log.

Roles: ``admin`` > ``pv_associate`` > ``viewer``. Tokens are signed JWTs.
Google/Microsoft OAuth activate when their client id/secret env vars are set;
a credential ``/auth/login`` always works for local/dev and role testing.
All auth events are written to ``logs/auth.log`` (timestamp | user | action).
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException

import config
from src.logging_config import get_logger

log = get_logger("auth")

ROLES = ("admin", "pv_associate", "viewer")
ROLE_RANK = {"viewer": 0, "pv_associate": 1, "admin": 2}

AUTH_SECRET = os.getenv("AUTH_SECRET", "dev-secret-change-me")
TOKEN_TTL = int(os.getenv("AUTH_TOKEN_TTL", str(8 * 3600)))
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "0") == "1"
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:8000")

OAUTH = {
    "google": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "microsoft": {
        "client_id": os.getenv("MICROSOFT_CLIENT_ID", ""),
        "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET", ""),
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo": "https://graph.microsoft.com/oidc/userinfo",
        "scope": "openid email profile",
    },
}


# --------------------------------------------------------------------------- #
# Audit log (timestamp | user | action)
# --------------------------------------------------------------------------- #
def audit(user: str, action: str) -> None:
    log.info("%s | %s", user or "anonymous", action)


# --------------------------------------------------------------------------- #
# User store
# --------------------------------------------------------------------------- #
def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.SQLITE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT, role TEXT,
        provider TEXT, created_at TEXT)""")
    return conn


def upsert_user(email: str, name: str, provider: str, role: str | None = None) -> dict[str, Any]:
    email = (email or "").lower().strip()
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            user = dict(row)
        else:
            assigned = role or ("admin" if email in ADMIN_EMAILS else "viewer")
            user = {"id": uuid.uuid4().hex, "email": email, "name": name or email,
                    "role": assigned, "provider": provider,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",
                         (user["id"], user["email"], user["name"], user["role"],
                          user["provider"], user["created_at"]))
            conn.commit()
            audit(email, f"user_created role={user['role']} provider={provider}")
        return user
    finally:
        conn.close()


def set_role(email: str, role: str, by: str) -> dict[str, Any]:
    if role not in ROLES:
        raise HTTPException(400, f"Invalid role. Use one of {ROLES}.")
    conn = _conn()
    try:
        conn.execute("UPDATE users SET role = ? WHERE email = ?", (role, email.lower()))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "User not found.")
    audit(by, f"role_change target={email} new_role={role}")
    return dict(row)


def list_users() -> list[dict[str, Any]]:
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_token(user: dict[str, Any]) -> str:
    now = int(time.time())
    payload = {"sub": user["email"], "name": user["name"], "role": user["role"],
               "provider": user.get("provider", ""), "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, AUTH_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, AUTH_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, f"Invalid or expired token: {exc}") from exc


# --------------------------------------------------------------------------- #
# FastAPI dependencies
# --------------------------------------------------------------------------- #
def optional_user(authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return decode_token(authorization.split(" ", 1)[1])


def require_user(user: dict[str, Any] | None = Depends(optional_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(401, "Authentication required.")
    return user


def require_role(minimum: str):
    """Dependency factory: require at least the given role."""
    def _dep(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        if ROLE_RANK.get(user.get("role"), -1) < ROLE_RANK[minimum]:
            audit(user.get("sub", "?"), f"forbidden need={minimum} have={user.get('role')}")
            raise HTTPException(403, f"Requires role '{minimum}' or higher.")
        return user
    return _dep


# --------------------------------------------------------------------------- #
# OAuth helpers
# --------------------------------------------------------------------------- #
def provider_enabled(provider: str) -> bool:
    p = OAUTH.get(provider)
    return bool(p and p["client_id"] and p["client_secret"])


def authorize_url(provider: str, state: str) -> str:
    from urllib.parse import urlencode

    p = OAUTH[provider]
    params = {"client_id": p["client_id"], "response_type": "code",
              "redirect_uri": f"{REDIRECT_BASE}/auth/{provider}/callback",
              "scope": p["scope"], "state": state, "access_type": "offline"}
    return f"{p['authorize']}?{urlencode(params)}"


def exchange_code(provider: str, code: str) -> dict[str, Any]:
    """Exchange an OAuth code for the user's profile (email, name)."""
    import httpx

    p = OAUTH[provider]
    redirect = f"{REDIRECT_BASE}/auth/{provider}/callback"
    with httpx.Client(timeout=15) as client:
        token_res = client.post(p["token"], data={
            "code": code, "client_id": p["client_id"], "client_secret": p["client_secret"],
            "redirect_uri": redirect, "grant_type": "authorization_code"})
        token_res.raise_for_status()
        access = token_res.json().get("access_token")
        info = client.get(p["userinfo"], headers={"Authorization": f"Bearer {access}"})
        info.raise_for_status()
        data = info.json()
    return {"email": data.get("email") or data.get("preferred_username", ""),
            "name": data.get("name") or data.get("given_name", "")}

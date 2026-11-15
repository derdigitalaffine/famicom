"""HTTP API: family identities, auth boundary and private XMPP adapter."""
from __future__ import annotations

import hmac
import json
import os
import re
import sqlite3
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import core, provision

COOKIE = "famicom_session"
SECURE = os.getenv("FAMICOM_SECURE_COOKIES", "true").lower() == "true"
FAILED_LOGINS = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    core.init_db()
    provision.sync()
    yield

app = FastAPI(title="FamiCom API", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)

class Login(BaseModel):
    username: str
    password: str

class NewUser(BaseModel):
    username: str
    display_name: str
    password: str
    role: str = "adult"
    extension: str | None = None

class UpdateUser(BaseModel):
    display_name: str | None = None
    role: str | None = None
    enabled: bool | None = None
    password: str | None = None

class ChangePassword(BaseModel):
    current_password: str
    new_password: str

class Trunk(BaseModel):
    enabled: bool = False
    host: str = ""
    username: str = ""
    password: str | None = None
    allowed_prefixes: list[str] = Field(default_factory=list, max_length=20)

def actor(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not authenticated")
    row = core.session(token)
    if row is None:
        raise HTTPException(401, "Session expired")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        given = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(given, row["csrf"]):
            raise HTTPException(403, "Invalid CSRF token")
    return row

def admin(row=Depends(actor)):
    if row["role"] != "admin":
        raise HTTPException(403, "Admin required")
    return row

def secret_auth(request: Request):
    authorization = request.headers.get("authorization", "")
    import base64
    expected = core.secret_file("FAMICOM_XMPP_AUTH_FILE")
    try:
        actual = base64.b64decode(authorization.split(" ", 1)[1]).decode() if authorization.startswith("Basic ") else ""
    except (ValueError, UnicodeDecodeError, IndexError):
        actual = ""
    if not expected or not hmac.compare_digest(actual, expected):
        raise HTTPException(401, "Unauthorized")

@app.get("/healthz")
def health():
    with core.database() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok"}

@app.get("/api/config")
def config():
    return {"domain": core.DOMAIN, "xmpp_websocket": "/xmpp-websocket", "sip_websocket": "/sip-ws",
            "group_domain": "conference." + core.DOMAIN, "sip_domain": core.DOMAIN}

@app.post("/api/auth/login")
def login(payload: Login, response: Response, request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = [x for x in FAILED_LOGINS.get(ip, []) if x > now - 300]
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many attempts; retry later")
    user = core.password_user(payload.username, payload.password)
    if user is None:
        attempts.append(now)
        FAILED_LOGINS[ip] = attempts
        raise HTTPException(401, "Invalid credentials")
    FAILED_LOGINS.pop(ip, None)
    token, csrf = core.create_session(user["id"])
    response.set_cookie(COOKIE, token, httponly=True, secure=SECURE, samesite="lax",
                        max_age=core.SESSION_SECONDS, path="/")
    return {"user": core.public_user(user), "csrf": csrf}

@app.get("/api/auth/me")
def me(row=Depends(actor)):
    return {"user": core.public_user(row), "csrf": row["csrf"]}

@app.post("/api/auth/logout")
def logout(response: Response, request: Request, row=Depends(actor)):
    core.destroy_session(request.cookies[COOKIE])
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}

@app.get("/api/users")
def users(row=Depends(actor)):
    with core.database() as db:
        rows = db.execute("SELECT * FROM users " + ("" if row["role"] == "admin" else "WHERE enabled=1 ") + "ORDER BY display_name COLLATE NOCASE").fetchall()
    return [core.public_user(item) for item in rows]

@app.get("/api/xmpp/search")
def xmpp_search(q: str = "", row=Depends(actor)):
    """Converse's XHR contact search. Only enrolled members are exposed."""
    query = q.strip().casefold()[:64]
    if len(query) < 2:
        return []
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with core.database() as db:
        matches = db.execute(
            "SELECT username, display_name FROM users WHERE enabled=1 "
            "AND (username LIKE ? ESCAPE '\\' OR display_name LIKE ? ESCAPE '\\') "
            "ORDER BY display_name COLLATE NOCASE LIMIT 30",
            (f"%{escaped}%", f"%{escaped}%")
        ).fetchall()
    return [{"jid": f"{member['username']}@{core.DOMAIN}", "fullname": member["display_name"]}
            for member in matches if member["username"] != row["username"]]

@app.post("/api/users", status_code=201)
def add_user(payload: NewUser, row=Depends(admin)):
    try:
        user = core.create_user(**payload.model_dump())
        synced = provision.sync()
        core.audit(row["id"], "user.created", user["username"])
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"user": user, "telephony_reload": synced}

@app.patch("/api/users/{user_id}")
def update_user(user_id: int, payload: UpdateUser, row=Depends(admin)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(422, "No changes")
    with core.database() as db:
        target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Unknown member")
        if "role" in updates and updates["role"] not in ("admin", "adult", "child"):
            raise HTTPException(422, "Unknown role")
        if updates.get("display_name") is not None and not 1 <= len(updates["display_name"].strip()) <= 80:
            raise HTTPException(422, "Invalid display name")
        removing_admin = target["role"] == "admin" and (
            ("role" in updates and updates["role"] != "admin") or updates.get("enabled") is False)
        if removing_admin:
            count = db.execute("SELECT count(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0]
            if count <= 1:
                raise HTTPException(409, "Cannot remove last admin")
        for field in ("display_name", "role", "enabled"):
            if field in updates and updates[field] is not None:
                db.execute(f"UPDATE users SET {field}=? WHERE id=?", (updates[field], user_id))
        if updates.get("password"):
            db.execute("UPDATE users SET password_hash=? WHERE id=?",
                       (core.hash_password(updates["password"]), user_id))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        if updates.get("enabled") is False:
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        updated = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    synced = provision.sync()
    core.audit(row["id"], "user.updated", str(user_id))
    return {"user": core.public_user(updated), "telephony_reload": synced}

@app.post("/api/account/password")
def change_password(payload: ChangePassword, row=Depends(actor)):
    if not core.valid_password(row["password_hash"], payload.current_password):
        raise HTTPException(401, "Current password invalid")
    try:
        core.reset_password(row["id"], payload.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "reauthentication_required": True}

@app.get("/api/telephony/credentials")
def credentials(row=Depends(actor)):
    return {"extension": row["extension"], "domain": core.DOMAIN,
            "sip_password": core.decrypt(row["sip_secret_cipher"]),
            "sip_websocket": "/sip-ws", "note": "Only reveal on explicit user action"}

@app.get("/api/admin/trunk")
def get_trunk(row=Depends(admin)):
    with core.database() as db:
        saved = db.execute("SELECT value FROM settings WHERE key='trunk'").fetchone()
    state = json.loads(saved["value"]) if saved else {}
    return {"enabled": bool(state.get("enabled", False)), "host": state.get("host", ""),
            "username": state.get("username", ""), "allowed_prefixes": state.get("allowed_prefixes", []),
            "password_set": bool(state.get("password_cipher"))}

@app.put("/api/admin/trunk")
def set_trunk(payload: Trunk, row=Depends(admin)):
    with core.database() as db:
        old = db.execute("SELECT value FROM settings WHERE key='trunk'").fetchone()
        saved = json.loads(old["value"]) if old else {}
        new = payload.model_dump(exclude={"password"})
        if any(not re.fullmatch(r"[0-9]{1,8}", p) for p in payload.allowed_prefixes):
            raise HTTPException(422, "Only numeric prefixes are allowed")
        if payload.enabled:
            if not re.fullmatch(r"[A-Za-z0-9.-]{4,253}", payload.host):
                raise HTTPException(422, "Invalid provider host")
            if not re.fullmatch(r"[A-Za-z0-9_.+@-]{1,128}", payload.username):
                raise HTTPException(422, "Invalid provider username")
            if not payload.allowed_prefixes:
                raise HTTPException(422, "Explicit number allow-list required")
            if not payload.password and not saved.get("password_cipher"):
                raise HTTPException(422, "Provider secret required")
        new["password_cipher"] = core.encrypt(payload.password) if payload.password else saved.get("password_cipher", "")
        db.execute("INSERT INTO settings(key,value) VALUES('trunk',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (json.dumps(new),))
    synced = provision.sync()
    core.audit(row["id"], "trunk.updated", "enabled" if payload.enabled else "disabled")
    return {"ok": True, "telephony_reload": synced}

@app.get("/internal/xmpp/{method}", response_class=PlainTextResponse, include_in_schema=False)
def xmpp_auth(method: str, request: Request):
    secret_auth(request)
    user = request.query_params.get("user", "")
    host = request.query_params.get("server", "")
    password = request.query_params.get("pass", "")
    if host != core.DOMAIN or not core.USERNAME_RE.fullmatch(user):
        return "false"
    if method == "check_password":
        return "true" if core.password_user(user, password) else "false"
    if method == "user_exists":
        with core.database() as db:
            found = db.execute("SELECT 1 FROM users WHERE username=? AND enabled=1", (user,)).fetchone()
        return "true" if found else "false"
    raise HTTPException(501, "Unsupported XMPP auth operation")

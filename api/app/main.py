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

from . import core, provision, ice as ice_module
from telephony.render import CallGroup, SipTrunk

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
    outbound_allowed: bool | None = None
    display_name: str | None = None
    role: str | None = None
    enabled: bool | None = None
    password: str | None = None

class ChangePassword(BaseModel):
    current_password: str
    new_password: str

class CallGroupInput(BaseModel):
    extension: str
    name: str = Field(min_length=1, max_length=80)
    members: list[str] = Field(min_length=1, max_length=20)

class ConferenceInput(BaseModel):
    extension: str
    name: str = Field(min_length=1, max_length=80)

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

@app.get("/api/telephony/ice")
def ice_settings(response: Response, row=Depends(actor)):
    """Same-origin, authenticated ICE config, never publicly cache credentials."""
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    try:
        return ice_module.ice_configuration(row["username"])
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

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
        effective_role = updates.get("role", target["role"])
        if updates.get("outbound_allowed") is True and effective_role == "child":
            raise HTTPException(422, "Children cannot place provider calls")
        removing_admin = target["role"] == "admin" and (
            ("role" in updates and updates["role"] != "admin") or updates.get("enabled") is False)
        if removing_admin:
            count = db.execute("SELECT count(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0]
            if count <= 1:
                raise HTTPException(409, "Cannot remove last admin")
        for field in ("display_name", "role", "enabled", "outbound_allowed"):
            if field in updates and updates[field] is not None:
                db.execute(f"UPDATE users SET {field}=? WHERE id=?", (updates[field], user_id))
        if effective_role == "child":
            db.execute("UPDATE users SET outbound_allowed=0 WHERE id=?", (user_id,))
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

@app.get("/api/telephony/directory")
def telephone_directory(row=Depends(actor)):
    with core.database() as db:
        groups = db.execute("SELECT extension,name,members_json FROM call_groups ORDER BY extension").fetchall()
        conferences = db.execute("SELECT extension,name FROM conference_rooms ORDER BY extension").fetchall()
    return {
        "groups": [{"extension": g["extension"], "name": g["name"], "members": json.loads(g["members_json"])} for g in groups],
        "conferences": [{"extension": c["extension"], "name": c["name"]} for c in conferences],
    }

@app.post("/api/admin/call-groups", status_code=201)
def save_call_group(payload: CallGroupInput, row=Depends(admin)):
    try:
        group = CallGroup(extension=payload.extension, members=tuple(payload.members))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with core.database() as db:
        allowed = {r["extension"] for r in db.execute("SELECT extension FROM users WHERE enabled=1")}
        if not set(group.members).issubset(allowed):
            raise HTTPException(422, "Group members must be existing enabled extensions")
        db.execute("INSERT INTO call_groups(extension,name,members_json) VALUES (?,?,?) "
                   "ON CONFLICT(extension) DO UPDATE SET name=excluded.name,members_json=excluded.members_json",
                   (group.extension, payload.name.strip(), json.dumps(group.members)))
    synced = provision.sync()
    core.audit(row["id"], "group.saved", group.extension)
    return {"extension": group.extension, "telephony_reload": synced}

@app.delete("/api/admin/call-groups/{extension}")
def delete_call_group(extension: str, row=Depends(admin)):
    with core.database() as db:
        result = db.execute("DELETE FROM call_groups WHERE extension=?", (extension,))
        if not result.rowcount:
            raise HTTPException(404, "Unknown group")
    synced = provision.sync()
    core.audit(row["id"], "group.deleted", extension)
    return {"ok": True, "telephony_reload": synced}

@app.post("/api/admin/conferences", status_code=201)
def save_conference(payload: ConferenceInput, row=Depends(admin)):
    if not re.fullmatch(r"3[0-9]{3}", payload.extension):
        raise HTTPException(422, "Conference number must be 3xxx")
    with core.database() as db:
        db.execute("INSERT INTO conference_rooms(extension,name) VALUES(?,?) "
                   "ON CONFLICT(extension) DO UPDATE SET name=excluded.name",
                   (payload.extension, payload.name.strip()))
    synced = provision.sync()
    core.audit(row["id"], "conference.saved", payload.extension)
    return {"extension": payload.extension, "telephony_reload": synced}

@app.delete("/api/admin/conferences/{extension}")
def delete_conference(extension: str, row=Depends(admin)):
    with core.database() as db:
        found = db.execute("DELETE FROM conference_rooms WHERE extension=?", (extension,))
        if not found.rowcount:
            raise HTTPException(404, "Unknown conference")
    synced = provision.sync()
    core.audit(row["id"], "conference.deleted", extension)
    return {"ok": True, "telephony_reload": synced}

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
        if len(set(payload.allowed_prefixes)) != len(payload.allowed_prefixes):
            raise HTTPException(422, "Duplicate prefixes")
        if any(not re.fullmatch(r"0[0-9]{4,12}", p) for p in payload.allowed_prefixes):
            raise HTTPException(422, "Each provider prefix must be a national/international prefix (0 + 4–12 digits)")
        if payload.enabled:
            if not re.fullmatch(r"[A-Za-z0-9.-]{4,253}", payload.host):
                raise HTTPException(422, "Invalid provider host")
            if not re.fullmatch(r"[A-Za-z0-9_.+@-]{1,128}", payload.username):
                raise HTTPException(422, "Invalid provider username")
            if not payload.allowed_prefixes:
                raise HTTPException(422, "Explicit number allow-list required")
            if not payload.password and not saved.get("password_cipher"):
                raise HTTPException(422, "Provider secret required")
            try:
                SipTrunk(name="famicom", proxy=payload.host, username=payload.username,
                         password=payload.password or core.decrypt(saved["password_cipher"]),
                         enabled=True, allowed_prefixes=tuple(payload.allowed_prefixes))
            except (ValueError, KeyError) as exc:
                raise HTTPException(422, str(exc)) from exc
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

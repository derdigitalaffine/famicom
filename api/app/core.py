"""Canonical identity store. All XMPP/SIP adapters derive from this database."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,31}$")
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
DB_PATH = Path(os.environ.get("FAMICOM_DB_PATH", "/data/famicom.sqlite3"))
DOMAIN = os.environ.get("FAMICOM_DOMAIN", "family.example.org").lower()
PROVISION_DIR = Path(os.environ.get("FAMICOM_PROVISION_DIR", "/provision"))
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
SESSION_SECONDS = 7 * 24 * 3600

def secret_file(name: str, default: str = "") -> str:
    filename = os.environ.get(name)
    if not filename:
        return default
    return Path(filename).read_text(encoding="utf-8").strip()

def cipher() -> Fernet:
    key = secret_file("FAMICOM_DB_KEY_FILE")
    if not key:
        raise RuntimeError("Missing encryption key file")
    return Fernet(key.encode("ascii"))

def encrypt(value: str) -> str:
    return cipher().encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    return cipher().decrypt(value.encode()).decode()

def hash_password(value: str) -> str:
    if len(value) < 12 or len(value) > 256:
        raise ValueError("Password must contain 12–256 characters")
    return HASHER.hash(value)

def valid_password(encoded: str, plain: str) -> bool:
    try:
        return HASHER.verify(encoded, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False

@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()

def init_db() -> None:
    if not DOMAIN_RE.fullmatch(DOMAIN):
        raise RuntimeError("Invalid FAMICOM_DOMAIN")
    with database() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('admin','adult','child')),
          password_hash TEXT NOT NULL,
          extension TEXT NOT NULL UNIQUE,
          sip_secret_cipher TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          csrf TEXT NOT NULL,
          expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          actor_id INTEGER,
          action TEXT NOT NULL,
          subject TEXT,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS call_groups (
          extension TEXT PRIMARY KEY CHECK (length(extension)=4),
          name TEXT NOT NULL,
          members_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conference_rooms (
          extension TEXT PRIMARY KEY CHECK (length(extension)=4),
          name TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        """)
        con.execute("INSERT OR IGNORE INTO conference_rooms(extension,name) VALUES (?,?)",
                    ("3000", "Familienkonferenz"))
        # Additive migration; the first Foundation release issued 200–999 extensions.
        # Convert them deterministically into 1200–1999 without discarding identities.
        columns = {item["name"] for item in con.execute("PRAGMA table_info(users)")}
        if "outbound_allowed" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN outbound_allowed INTEGER NOT NULL DEFAULT 0")
        current = con.execute("SELECT id, extension FROM users ORDER BY id").fetchall()
        used = {row["extension"] for row in current if re.fullmatch(r"[12][0-9]{3}", row["extension"])}
        for row in current:
            old = row["extension"]
            if re.fullmatch(r"[12][0-9]{3}", old):
                continue
            preferred = "1" + old if re.fullmatch(r"[2-9][0-9]{2}", old) else None
            new_extension = preferred if preferred and preferred not in used else next(
                (str(value) for value in range(1200, 3000) if str(value) not in used), None
            )
            if not new_extension:
                raise RuntimeError("No available 4-digit SIP extension for migration")
            con.execute("UPDATE users SET extension=?,outbound_allowed=0 WHERE id=?",
                        (new_extension, row["id"]))
            con.execute("INSERT INTO audit(actor_id,action,subject,created_at) VALUES (NULL,?,?,?)",
                        ("sip.extension.migrated", str(row["id"]) + ":" + old + "->" + new_extension,
                         int(time.time())))
            used.add(new_extension)
        # Existing admins/adults are not implicitly permitted to place paid calls.
        con.execute("UPDATE users SET outbound_allowed=0 WHERE role='child'")

def public_user(row) -> dict:
    return {
        "id": row["id"], "username": row["username"], "display_name": row["display_name"],
        "jid": f"{row['username']}@{DOMAIN}", "role": row["role"],
        "extension": row["extension"], "enabled": bool(row["enabled"]),
        "outbound_allowed": bool(row["outbound_allowed"])
    }

def check_username(username: str) -> str:
    username = username.lower().strip()
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Username must be 3–32 chars, lowercase ASCII, starts with a letter")
    return username

def create_user(username: str, display_name: str, role: str, password: str, extension: str | None = None) -> dict:
    username = check_username(username)
    if role not in ("admin", "adult", "child"):
        raise ValueError("Invalid role")
    display_name = display_name.strip()
    if not 1 <= len(display_name) <= 80:
        raise ValueError("Display name must be 1–80 characters")
    hashed = hash_password(password)
    with database() as con:
        if extension is None:
            existing = {r[0] for r in con.execute("SELECT extension FROM users")}
            extension = next((str(i) for i in range(1200, 3000) if str(i) not in existing), None)
            if extension is None:
                raise ValueError("No free extension")
        if not re.fullmatch(r"[12][0-9]{3}", extension):
            raise ValueError("SIP extensions must be between 1000 and 2999 (four digits)")
        sip_secret = secrets.token_urlsafe(32)
        cur = con.execute(
            "INSERT INTO users(username,display_name,role,password_hash,extension,sip_secret_cipher,created_at) VALUES (?,?,?,?,?,?,?)",
            (username, display_name, role, hashed, extension, encrypt(sip_secret), int(time.time())),
        )
        con.execute("INSERT INTO audit(actor_id,action,subject,created_at) VALUES (NULL,?,?,?)",
                    ("user.created", username, int(time.time())))
        row = con.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return public_user(row)

def password_user(username: str, password: str):
    with database() as con:
        row = con.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username.lower(),)).fetchone()
    if row and valid_password(row["password_hash"], password):
        return row
    # Avoid short-circuiting cost for unknown users.
    if not row:
        valid_password(_DUMMY_HASH, password)
    return None

_DUMMY_HASH = HASHER.hash("nonexistent-account-password-never-used")

def create_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(40)
    csrf = secrets.token_urlsafe(32)
    with database() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        con.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES (?,?,?,?)",
                    (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, int(time.time()) + SESSION_SECONDS))
    return token, csrf

def session(token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database() as con:
        return con.execute("""
            SELECT u.*, s.csrf FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1
        """, (token_hash, int(time.time()))).fetchone()

def destroy_session(token: str) -> None:
    with database() as con:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

def reset_password(user_id: int, password: str) -> None:
    hashed = hash_password(password)
    with database() as con:
        con.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed, user_id))
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))

def audit(actor_id: int, action: str, subject: str = ""):
    with database() as con:
        con.execute("INSERT INTO audit(actor_id,action,subject,created_at) VALUES (?,?,?,?)",
                    (actor_id, action, subject, int(time.time())))

"""Fail-closed FreeSWITCH XML generation. No Docker socket is ever mounted."""
from __future__ import annotations

import os
import re
import socket
from pathlib import Path
from xml.sax.saxutils import escape

from .core import DOMAIN, PROVISION_DIR, database, decrypt, secret_file

def xml(value: str) -> str:
    return escape(str(value), {'"': '&quot;', "'": '&apos;'})

def atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(value, encoding="utf-8")
    os.chmod(temp, 0o640)
    os.replace(temp, path)

def render_users() -> None:
    with database() as con:
        rows = con.execute("SELECT * FROM users WHERE enabled=1 ORDER BY extension").fetchall()
    users = []
    for row in rows:
        uid = xml(row["extension"])
        name = xml(row["display_name"])
        password = xml(decrypt(row["sip_secret_cipher"]))
        users.append(
            f'<user id="{uid}"><params><param name="password" value="{password}"/>'
            f'<param name="vm-password" value="{uid}"/></params><variables>'
            f'<variable name="user_context" value="default"/>'
            f'<variable name="effective_caller_id_name" value="{name}"/>'
            f'<variable name="effective_caller_id_number" value="{uid}"/>'
            f'<variable name="outbound_caller_id_number" value="{uid}"/>'
            f'</variables></user>'
        )
    atomic_write(PROVISION_DIR / "directory/default/users.xml", "<include>\n" + "\n".join(users) + "\n</include>\n")

def render_trunk() -> None:
    with database() as con:
        row = con.execute("SELECT value FROM settings WHERE key='trunk'").fetchone()
    import json
    conf = json.loads(row["value"]) if row else {}
    enabled = bool(conf.get("enabled", False))
    prefix = [p for p in conf.get("allowed_prefixes", []) if re.fullmatch(r"[0-9]{1,8}", p)]
    if not enabled or not prefix:
        atomic_write(PROVISION_DIR / "sip_profiles/external/famicom.xml", "<include/>\n")
        atomic_write(PROVISION_DIR / "dialplan/default/30-outbound.xml", "<include/>\n")
        return
    host = conf.get("host", "")
    if not re.fullmatch(r"[A-Za-z0-9.-]{4,253}", host):
        raise ValueError("Invalid SIP provider")
    user = conf.get("username", "")
    if not re.fullmatch(r"[A-Za-z0-9_.+@-]{1,128}", user):
        raise ValueError("Invalid trunk username")
    password = decrypt(conf["password_cipher"])
    gateway = ('<include><gateway name="famicom"><param name="proxy" value="' + xml(host) + '"/>'
               '<param name="username" value="' + xml(user) + '"/>'
               '<param name="password" value="' + xml(password) + '"/>'
               '<param name="register" value="true"/></gateway></include>\n')
    # Prefixes are literal numeric strings, not user-controlled regex.
    pattern = "|".join(re.escape(p) for p in prefix)
    outgoing = ("""<include><extension name="approved-outbound"><condition field="destination_number" expression="^0((?:%s)[0-9]{3,14})$"><action application="set" data="hangup_after_bridge=true"/><action application="bridge" data="sofia/gateway/famicom/$1"/></condition></extension></include>\n""" % pattern)
    atomic_write(PROVISION_DIR / "sip_profiles/external/famicom.xml", gateway)
    atomic_write(PROVISION_DIR / "dialplan/default/30-outbound.xml", outgoing)

def reload_xml() -> bool:
    """Internal ESL only. A missed reload is retried at next service restart."""
    password = secret_file("FAMICOM_ESL_PASSWORD_FILE")
    if not password:
        return False
    try:
        with socket.create_connection(("freeswitch", 8021), timeout=2) as conn:
            conn.settimeout(3)
            conn.recv(4096)
            conn.sendall(("auth " + password + "\n\n").encode())
            if b"+OK accepted" not in conn.recv(4096):
                return False
            conn.sendall(b"api reloadxml\n\n")
            return b"+OK" in conn.recv(4096)
    except (OSError, TimeoutError):
        return False

def sync() -> bool:
    render_users()
    render_trunk()
    return reload_xml()

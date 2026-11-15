"""Canonical FreeSWITCH XML publisher.

FreeSWITCH consumes the *same* fail-closed telephony.render contract tested
in the independent routing library. Database and caller secret never enter logs.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
from pathlib import Path

from telephony.render import (
    CallGroup, IncomingRoute, SipTrunk, SipUser,
    render_directory, render_dialplan, render_gateway, render_public_dialplan,
    sip_ha1,
)

from .core import DOMAIN, PROVISION_DIR, database, decrypt, secret_file

LOG = logging.getLogger(__name__)
_LOCK = threading.RLock()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _trunk(config: dict) -> SipTrunk | None:
    if not config.get("enabled"):
        return None
    try:
        return SipTrunk(
            name="famicom", proxy=config.get("host", ""),
            username=config.get("username", ""),
            password=decrypt(config.get("password_cipher", "")),
            enabled=True, allowed_prefixes=tuple(config.get("allowed_prefixes", [])),
        )
    except (ValueError, KeyError, TypeError):
        LOG.warning("Rejecting invalid stored SIP trunk configuration")
        return None


def configuration_xml() -> dict[str, str]:
    """Generate a complete, consistent snapshot before replacing any config."""
    with database() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        groups = conn.execute("SELECT extension,name,members_json FROM call_groups ORDER BY extension").fetchall()
        rooms = conn.execute("SELECT extension FROM conference_rooms ORDER BY extension").fetchall()
        saved = conn.execute("SELECT value FROM settings WHERE key='trunk'").fetchone()
    users = [
        SipUser(username=row["username"], extension=row["extension"],
                ha1=sip_ha1(row["extension"], DOMAIN, decrypt(row["sip_secret_cipher"])),
                role=row["role"], enabled=bool(row["enabled"]),
                outbound_allowed=bool(row["outbound_allowed"]))
        for row in rows
    ]
    enabled_extensions = {user.extension for user in users if user.enabled}
    call_groups = []
    for item in groups:
        members = tuple(ext for ext in json.loads(item["members_json"]) if ext in enabled_extensions)
        if members:
            call_groups.append(CallGroup(extension=item["extension"], members=members))
    trunk_config = json.loads(saved["value"]) if saved else {}
    trunk = _trunk(trunk_config)
    return {
        "directory/default.xml": render_directory(DOMAIN, users),
        "dialplan/default.xml": render_dialplan(
            DOMAIN, groups=call_groups, conference_numbers=tuple(item["extension"] for item in rooms), trunk=trunk
        ),
        "dialplan/public.xml": render_public_dialplan(DOMAIN),
        "sip_profiles/external/famicom.xml": render_gateway(trunk),
    }


def render_users() -> None:
    """Backwards-compatible helper; always render *all* dependent contexts."""
    publish()


def render_trunk() -> None:
    """Backwards-compatible helper; does not leave directory/dialplan stale."""
    publish()


def publish() -> None:
    with _LOCK:
        files = configuration_xml()
        for name, content in files.items():
            atomic_write(PROVISION_DIR / name, content)
        # Old Foundation generated a cleartext SIP secret file. It must not
        # survive migration even though the new directory no longer includes it.
        (PROVISION_DIR / "directory/default/users.xml").unlink(missing_ok=True)
        for stale in ("dialplan/default/10-internal.xml", "dialplan/default/20-features.xml",
                      "dialplan/default/30-outbound.xml"):
            (PROVISION_DIR / stale).unlink(missing_ok=True)


def _receive_packet(stream: socket.socket) -> bytes:
    data = b""
    while b"\n\n" not in data and b"\r\n\r\n" not in data and len(data) < 50000:
        chunk = stream.recv(8192)
        if not chunk:
            break
        data += chunk
    return data


def reload_xml() -> bool:
    """One authenticated ESL control channel; never exposed outside Compose."""
    password = secret_file("FAMICOM_ESL_PASSWORD_FILE")
    if not password:
        return False
    try:
        with socket.create_connection(("freeswitch", 8021), timeout=3) as conn:
            conn.settimeout(5)
            _receive_packet(conn)
            conn.sendall(("auth " + password + "\n\n").encode())
            if b"+OK accepted" not in _receive_packet(conn):
                return False
            conn.sendall(b"api reloadxml\n\n")
            result = _receive_packet(conn)
            if b"+OK" not in result or b"-ERR" in result:
                return False
            conn.sendall(b"api sofia profile external rescan\n\n")
            _receive_packet(conn)
            return True
    except (OSError, TimeoutError) as exc:
        LOG.warning("FreeSWITCH XML reload unavailable (%s)", type(exc).__name__)
        return False


def sync() -> bool:
    publish()
    return reload_xml()

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


def as_freeswitch_include(document: str) -> str:
    """Strip XML declarations: these fragments are embedded in freeswitch.xml."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(document)
    if root.tag != "include":
        raise ValueError("Expected FreeSWITCH include fragment")
    return ET.tostring(root, encoding="unicode") + "\n"


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
    # Publish the canonical domain + user list as ONE XML fragment. Nested
    # FreeSWITCH X-PRE-PROCESS includes are brittle under live reloads and
    # were hiding otherwise-readable users from the active directory.
    directory_document = as_freeswitch_include(render_directory(DOMAIN, users))
    return {
        "directory/default.xml": directory_document,
        "dialplan/default.xml": as_freeswitch_include(render_dialplan(
            DOMAIN, groups=call_groups, conference_numbers=tuple(item["extension"] for item in rooms), trunk=trunk
        )),
        "dialplan/public.xml": as_freeswitch_include(render_public_dialplan(DOMAIN)),
        "sip_profiles/external/famicom.xml": as_freeswitch_include(render_gateway(trunk)),
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
        # No second account copy: old Foundation/previous migration snippets
        # are deleted after the canonical domain XML is atomically published.
        (PROVISION_DIR / "directory/default/users.xml").unlink(missing_ok=True)
        for stale in ("dialplan/default/10-internal.xml", "dialplan/default/20-features.xml",
                      "dialplan/default/30-outbound.xml"):
            (PROVISION_DIR / stale).unlink(missing_ok=True)


class ESLFrames:
    """Framed FreeSWITCH Event Socket reader with split-recv support.

    A header delimiter does not mark end of an API response: the body is
    signaled by Content-Length and may arrive in a later TCP segment. Preserve
    leftover bytes for subsequent responses, without exposing ESL secrets.
    """
    def __init__(self, stream: socket.socket):
        self.stream = stream
        self.pending = b""

    def read(self) -> tuple[dict[str, str], bytes]:
        while True:
            a = self.pending.find(b"\r\n\r\n")
            b = self.pending.find(b"\n\n")
            choices = [(a, 4)] if a >= 0 else []
            if b >= 0:
                choices.append((b, 2))
            if choices:
                stop, width = min(choices)
                break
            if len(self.pending) > 65536:
                raise ValueError("Oversized ESL header")
            chunk = self.stream.recv(8192)
            if not chunk:
                raise ConnectionError("Unexpected ESL EOF")
            self.pending += chunk
        raw_headers = self.pending[:stop].decode("utf-8", errors="replace")
        headers = {}
        for line in raw_headers.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        raw_length = headers.get("content-length", "0")
        if not raw_length.isdecimal():
            raise ValueError("Invalid ESL Content-Length")
        length = int(raw_length)
        if length > 1024 * 1024:
            raise ValueError("Oversized ESL response")
        body_and_rest = self.pending[stop+width:]
        while len(body_and_rest) < length:
            chunk = self.stream.recv(8192)
            if not chunk:
                raise ConnectionError("Unexpected ESL body EOF")
            body_and_rest += chunk
        body = body_and_rest[:length]
        self.pending = body_and_rest[length:]
        return headers, body


def reload_xml() -> bool:
    """Authenticated private ESL with complete frame handling."""
    password = secret_file("FAMICOM_ESL_PASSWORD_FILE")
    if not password:
        return False
    try:
        with socket.create_connection(("freeswitch", 8021), timeout=3) as conn:
            conn.settimeout(6)
            reader = ESLFrames(conn)
            greeting, _ = reader.read()
            if greeting.get("content-type") != "auth/request":
                return False
            conn.sendall(("auth " + password + "\n\n").encode())
            auth_headers, _ = reader.read()
            if "+OK accepted" not in auth_headers.get("reply-text", ""):
                return False
            conn.sendall(b"api reloadxml\n\n")
            headers, body = reader.read()
            if headers.get("content-type") != "api/response":
                return False
            response = body.strip()
            if not response.startswith(b"+OK") or b"-ERR" in response:
                return False
            conn.sendall(b"api sofia profile external rescan\n\n")
            reader.read()
            return True
    except (OSError, TimeoutError, ValueError, ConnectionError) as exc:
        LOG.warning("FreeSWITCH XML reload unavailable (%s)", type(exc).__name__)
        return False


def sync() -> bool:
    publish()
    return reload_xml()

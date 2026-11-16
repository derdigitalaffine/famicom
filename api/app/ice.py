"""Authenticated, ephemeral TURN REST credentials (RFC-style coturn shared secret).

No persistent TURN passwords are stored or returned. Disabled-by-default
installation never invents an external STUN/TURN service.
"""
import base64
import hashlib
import hmac
import ipaddress
import os
import time

from . import core

TURN_TTL_SECONDS = 3600


def _valid_host(value: str) -> bool:
    if core.DOMAIN_RE.fullmatch(value):
        return True
    try:
        ipaddress.ip_address(value)
        return ":" not in value  # URLs below require unbracketed IPv4 only
    except ValueError:
        return False


def ice_configuration(username: str) -> dict:
    if os.getenv("FAMICOM_TURN_ENABLED", "false").lower() != "true":
        return {"enabled": False, "iceServers": [], "expires_at": None}
    host = os.getenv("FAMICOM_TURN_HOST", "").strip().lower()
    key = core.secret_file("FAMICOM_TURN_SECRET_FILE")
    if not _valid_host(host) or len(key) < 32:
        raise RuntimeError("TURN is enabled but the domain or authentication secret is invalid")
    expires = int(time.time()) + TURN_TTL_SECONDS
    temporary_username = f"{expires}:{username}"
    digest = hmac.new(key.encode("utf-8"), temporary_username.encode("utf-8"), hashlib.sha1).digest()
    password = base64.b64encode(digest).decode("ascii")
    return {
        "enabled": True,
        "expires_at": expires,
        "iceServers": [
            {"urls": [f"stun:{host}:3478"]},
            {"urls": [f"turn:{host}:3478?transport=udp", f"turn:{host}:3478?transport=tcp"],
             "username": temporary_username, "credential": password},
        ],
    }

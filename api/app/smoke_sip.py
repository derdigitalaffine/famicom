"""Live SIP REGISTER 401-Digest challenge/response smoke test.

Runs INSIDE the API container with generated first-user credentials. Never prints
credentials. This verifies SIP provisioning; it does not place a real RTP call.
"""
import hashlib
import os
import random
import re
import secrets
import socket
from .core import DOMAIN, database, decrypt

def challenge_params(value):
    return {item.group(1).lower(): item.group(2) or item.group(3)
            for item in re.finditer(r'([A-Za-z_-]+)=(?:"([^"]*)"|([^,\s]+))', value)}

def md5(content):
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def build_digest(header, username, password, method, uri):
    values = challenge_params(header)
    realm = values.get("realm", DOMAIN)
    nonce = values.get("nonce")
    if not nonce:
        raise AssertionError("No SIP digest nonce")
    algorithm = values.get("algorithm", "MD5").upper()
    if algorithm not in ("MD5",):
        raise AssertionError("Unexpected SIP challenge digest algorithm: " + algorithm)
    ha1 = md5(f"{username}:{realm}:{password}")
    ha2 = md5(f"{method}:{uri}")
    qop_list = [part.strip() for part in values.get("qop", "").split(",")]
    if "auth" in qop_list:
        cnonce = secrets.token_hex(8)
        nc = "00000001"
        response = md5(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}")
        suffix = f', qop=auth, nc={nc}, cnonce="{cnonce}"'
    elif not values.get("qop"):
        response = md5(f"{ha1}:{nonce}:{ha2}")
        suffix = ""
    else:
        raise AssertionError("Unsupported SIP digest challenge quality")
    return (
        f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
        f'uri="{uri}", response="{response}", algorithm=MD5{suffix}'
    )

def register():
    with database() as db:
        user = db.execute("SELECT extension,sip_secret_cipher FROM users WHERE enabled=1 ORDER BY id LIMIT 1").fetchone()
    assert user, "No provisioned SIP family member"
    extension = user["extension"]
    password = decrypt(user["sip_secret_cipher"])
    gateway = socket.gethostbyname("freeswitch")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.bind(("0.0.0.0", 0))
        client.settimeout(8)
        # Resolve our own bridge address by connecting to the target.
        client.connect((gateway, 5060))
        addr, port = client.getsockname()
        tag, callid = secrets.token_hex(8), secrets.token_hex(12)
        uri = "sip:" + DOMAIN
        def send(seq, authorization=""):
            branch = "z9hG4bK" + secrets.token_hex(8)
            fields = [
                f"REGISTER {uri} SIP/2.0",
                f"Via: SIP/2.0/UDP {addr}:{port};branch={branch};rport",
                "Max-Forwards: 70",
                f"From: <sip:{extension}@{DOMAIN}>;tag={tag}",
                f"To: <sip:{extension}@{DOMAIN}>",
                f"Call-ID: {callid}",
                f"CSeq: {seq} REGISTER",
                f"Contact: <sip:{extension}@{addr}:{port};transport=udp>",
                "Expires: 180",
                "User-Agent: FamiCom-Integration-Smoke/1",
            ]
            if authorization:
                fields.append("Authorization: " + authorization)
            fields.extend(["Content-Length: 0", "", ""])
            client.send("\r\n".join(fields).encode())
            response = ""
            for _ in range(5):
                packet = client.recv(16384).decode(errors="replace")
                response = packet
                status = re.search(r"^SIP/2.0\s+(\d{3})", packet)
                if not status:
                    continue
                if int(status.group(1)) < 200:
                    continue
                return int(status.group(1)), response
            raise AssertionError("No final SIP response")
        code, first = send(1)
        if code not in (401, 407):
            raise AssertionError(f"Unauthenticated SIP REGISTER should challenge, got {code}")
        challenge_name = "Proxy-Authenticate" if code == 407 else "WWW-Authenticate"
        challenge = next((line.split(":", 1)[1].strip() for line in first.splitlines()
                          if line.lower().startswith(challenge_name.lower() + ":")), "")
        if not challenge:
            raise AssertionError("Missing SIP authentication challenge")
        realm = challenge_params(challenge).get("realm")
        if realm != DOMAIN:
            raise AssertionError("SIP challenge realm is not canonical family domain")
        authorization = build_digest(challenge, extension, password, "REGISTER", uri)
        code, _ = send(2, authorization)
        if code != 200:
            raise AssertionError(f"Valid generated SIP account registration was rejected: {code}")
    return extension

if __name__ == "__main__":
    if os.getenv("FAMICOM_TEST_SIP") != "1":
        raise SystemExit("Only enable SIP smoke test in isolated CI/staging")
    extension = register()
    print(f"SIP smoke test passed: extension {extension} registered with digest challenge")

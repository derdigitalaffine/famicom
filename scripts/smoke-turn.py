#!/usr/bin/env python3
"""Real coturn Allocate challenge/response using API-issued TURN REST credentials.

Run only against a disposable test installation. Does not log TURN username,
credential, shared secret, relayed IP address, or SDP.
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import socket
import struct
import sys
import time

COOKIE = 0x2112A442
REQUEST = 0x0003
SUCCESS = 0x0103
ERROR = 0x0113
ATTR_USERNAME = 0x0006
ATTR_MESSAGE_INTEGRITY = 0x0008
ATTR_ERROR_CODE = 0x0009
ATTR_REALM = 0x0014
ATTR_NONCE = 0x0015
ATTR_XOR_RELAYED_ADDRESS = 0x0016
ATTR_REQUESTED_TRANSPORT = 0x0019


def attribute(kind, value):
    return struct.pack("!HH", kind, len(value)) + value + b"\0" * ((-len(value)) % 4)


def frame(msg_type, txn, payload):
    return struct.pack("!HHI", msg_type, len(payload), COOKIE) + txn + payload


def parse(message, txn):
    if len(message) < 20:
        raise ValueError("Truncated TURN response")
    msg_type, length, cookie = struct.unpack("!HHI", message[:8])
    if cookie != COOKIE or message[8:20] != txn:
        raise ValueError("TURN response does not match transaction")
    if len(message) < 20 + length:
        raise ValueError("Truncated TURN attributes")
    attributes = {}
    position = 20
    end = 20 + length
    while position + 4 <= end:
        kind, size = struct.unpack("!HH", message[position:position + 4])
        position += 4
        if position + size > end:
            raise ValueError("Malformed TURN attribute")
        attributes.setdefault(kind, []).append(message[position:position + size])
        position += size + ((-size) % 4)
    return msg_type, attributes


def exchange(sock, payload, txn):
    request = frame(REQUEST, txn, payload)
    for _ in range(4):
        sock.send(request)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                response = sock.recv(65535)
            except socket.timeout:
                break
            if response[8:20] != txn:
                continue
            return parse(response, txn)
    raise TimeoutError("No TURN Allocate response")


def authenticated_payload(txn, username, realm, nonce, password):
    fields = (
        attribute(ATTR_REQUESTED_TRANSPORT, b"\x11\0\0\0")
        + attribute(ATTR_USERNAME, username.encode())
        + attribute(ATTR_REALM, realm)
        + attribute(ATTR_NONCE, nonce)
    )
    # RFC 5389: HMAC-SHA1 uses the MD5 long-term credential key, while the
    # header length points to the end of the (not yet appended) MI attribute.
    key = hashlib.md5(username.encode() + b":" + realm + b":" + password.encode()).digest()
    message = frame(REQUEST, txn, fields + b"\0" * 24)
    digest = hmac.new(key, message[:20 + len(fields)], hashlib.sha1).digest()
    return fields + attribute(ATTR_MESSAGE_INTEGRITY, digest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3478)
    parser.add_argument("--ice-file", required=True)
    args = parser.parse_args()
    with open(args.ice_file, encoding="utf-8") as stream:
        ice = json.load(stream)
    if not ice.get("enabled"):
        raise RuntimeError("API did not enable TURN")
    if not (int(time.time()) < ice.get("expires_at", 0) <= int(time.time()) + 3600):
        raise RuntimeError("Invalid API-issued TURN expiry")
    servers = [item for item in ice["iceServers"] if "username" in item]
    if len(servers) != 1:
        raise RuntimeError("Expected exactly one authenticated TURN server")
    username = servers[0]["username"]
    password = servers[0]["credential"]
    if not username or not password:
        raise RuntimeError("Missing temporary TURN credentials")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        sock.connect((args.host, args.port))
        txn = secrets.token_bytes(12)
        kind, attrs = exchange(sock, attribute(ATTR_REQUESTED_TRANSPORT, b"\x11\0\0\0"), txn)
        if kind != ERROR or ATTR_NONCE not in attrs or ATTR_REALM not in attrs:
            raise RuntimeError("Unauthenticated TURN Allocate did not issue a challenge")
        code = attrs.get(ATTR_ERROR_CODE, [b""])[0]
        if len(code) < 4 or code[2] * 100 + code[3] != 401:
            raise RuntimeError("Unexpected TURN authentication challenge status")
        realm, nonce = attrs[ATTR_REALM][0], attrs[ATTR_NONCE][0]
        txn = secrets.token_bytes(12)
        kind, attrs = exchange(sock, authenticated_payload(txn, username, realm, nonce, password), txn)
        if kind != SUCCESS or ATTR_XOR_RELAYED_ADDRESS not in attrs:
            error = attrs.get(ATTR_ERROR_CODE, [b""])[0]
            reason = (error[2] * 100 + error[3]) if len(error) >= 4 else "unknown"
            raise RuntimeError("Authenticated TURN Allocate failed (code %s)" % reason)
    print("TURN live Allocate PASS: authenticated API-issued credentials accepted by coturn")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TimeoutError, RuntimeError) as exc:
        print("TURN smoke failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)

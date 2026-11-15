"""Strict, opt-in FreeSWITCH XML for private family calling.

No runtime side effects or external calls. Sofia must be configured separately
with authenticated private and IP-restricted provider profiles.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5
import re
from xml.etree import ElementTree as ET


DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
NAME = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
EXT = re.compile(r"^[12][0-9]{3}$")
GROUP = re.compile(r"^6[0-9]{3}$")
ROOM = re.compile(r"^3[0-9]{3}$")
DID = re.compile(r"^\+?[0-9]{6,15}$")
PREFIX = re.compile(r"^0[0-9]{4,12}$")
HEX = re.compile(r"^[0-9a-f]{32}$")


def check(value: str, pattern: re.Pattern, label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("Invalid " + label)
    return value


def secret(value: str) -> str:
    if (not isinstance(value, str) or not 12 <= len(value) <= 256
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in value)
            or any(ch in value for ch in ("$", "{", "}"))):
        raise ValueError("Secret must be 12..256 printable ASCII characters without variable expansion")
    return value


def sip_ha1(extension: str, realm: str, password: str) -> str:
    check(extension, EXT, "extension")
    check(realm, DOMAIN, "realm")
    secret(password)
    return md5(f"{extension}:{realm}:{password}".encode()).hexdigest()


def fs_var(name: str) -> str:
    return chr(36) + "{" + name + "}"


def xml(root: ET.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


@dataclass(frozen=True)
class SipUser:
    username: str
    extension: str
    ha1: str
    role: str = "adult"
    enabled: bool = True
    outbound_allowed: bool = False

    def __post_init__(self):
        check(self.username, NAME, "username")
        check(self.extension, EXT, "extension")
        check(self.ha1, HEX, "SIP HA1")
        if self.role not in ("admin", "adult", "child", "guest"):
            raise ValueError("Invalid role")
        if self.role in ("child", "guest") and self.outbound_allowed:
            raise ValueError("Child/guest cannot have PSTN privileges")


@dataclass(frozen=True)
class CallGroup:
    extension: str
    members: tuple[str, ...]

    def __post_init__(self):
        check(self.extension, GROUP, "group")
        if not 1 <= len(self.members) <= 20 or len(set(self.members)) != len(self.members):
            raise ValueError("Group membership must contain 1..20 unique extensions")
        for member in self.members:
            check(member, EXT, "member extension")


@dataclass(frozen=True)
class IncomingRoute:
    did: str
    extension: str

    def __post_init__(self):
        check(self.did, DID, "DID")
        check(self.extension, EXT, "destination extension")


@dataclass(frozen=True)
class SipTrunk:
    name: str
    proxy: str
    username: str
    password: str
    enabled: bool = False
    allowed_prefixes: tuple[str, ...] = ()

    def __post_init__(self):
        check(self.name, NAME, "gateway name")
        check(self.proxy, DOMAIN, "SIP proxy")
        check(self.username, NAME, "gateway account")
        secret(self.password)
        if self.enabled and not self.allowed_prefixes:
            raise ValueError("Enabled trunk requires allowlist")
        if len(self.allowed_prefixes) > 30 or len(self.allowed_prefixes) != len(set(self.allowed_prefixes)):
            raise ValueError("Invalid allowlist count")
        for prefix in self.allowed_prefixes:
            check(prefix, PREFIX, "outbound prefix")
            if prefix.startswith(("001", "002", "003", "009", "0900", "0137", "0180")):
                raise ValueError("Premium or broad prefix requires separate policy approval")


def domain_element(domain: str, users) -> ET.Element:
    check(domain, DOMAIN, "SIP realm")
    root = ET.Element("domain", name=domain)
    params = ET.SubElement(root, "params")
    contact = fs_var("sofia_contact(" + fs_var("dialed_user") + "@" + fs_var("dialed_domain") + ")")
    ET.SubElement(params, "param", name="dial-string",
                  value="{presence_id=" + fs_var("dialed_user") + "@" + fs_var("dialed_domain") + "}" + contact)
    entries = ET.SubElement(ET.SubElement(ET.SubElement(root, "groups"), "group", name="default"), "users")
    seen_names, seen_exts = set(), set()
    for user in users:
        if not isinstance(user, SipUser):
            raise ValueError("Expected SipUser")
        if user.username in seen_names or user.extension in seen_exts:
            raise ValueError("Duplicate family user or extension")
        seen_names.add(user.username)
        seen_exts.add(user.extension)
        if not user.enabled:
            continue
        u = ET.SubElement(entries, "user", id=user.extension)
        ET.SubElement(ET.SubElement(u, "params"), "param", name="a1-hash", value=user.ha1)
        variables = ET.SubElement(u, "variables")
        for name, value in {
            "user_context": "famicom-internal",
            "accountcode": user.username,
            "family_role": user.role,
            "outbound_allowed": "true" if user.outbound_allowed and user.role in ("admin", "adult") else "false",
            "effective_caller_id_number": user.extension,
        }.items():
            ET.SubElement(variables, "variable", name=name, value=value)
    return root


def render_directory(domain: str, users) -> str:
    root = ET.Element("include")
    root.append(domain_element(domain, users))
    return xml(root)


def render_directory_response(domain: str, users) -> str:
    root = ET.Element("document", type="freeswitch/xml")
    ET.SubElement(root, "section", name="directory").append(domain_element(domain, users))
    return xml(root)


def add_route(ctx: ET.Element, name: str, expression: str, actions, *, authenticated=True, permission=None):
    ext = ET.SubElement(ctx, "extension", name=name)
    if authenticated:
        ET.SubElement(ext, "condition", field=fs_var("sip_authorized"),
                      expression="^true$", **{"break": "on-false"})
        ET.SubElement(ext, "condition", field=fs_var("sip_auth_username"),
                      expression="^[12][0-9]{3}$", **{"break": "on-false"})
    if permission:
        ET.SubElement(ext, "condition", field=permission,
                      expression="^true$", **{"break": "on-false"})
    match = ET.SubElement(ext, "condition", field="destination_number", expression=expression)
    for application, data in actions:
        ET.SubElement(match, "action", application=application, data=data)


def render_dialplan(domain: str, groups=(), conference_numbers=(), trunk: SipTrunk | None = None) -> str:
    check(domain, DOMAIN, "SIP realm")
    root = ET.Element("include")
    ctx = ET.SubElement(root, "context", name="famicom-internal")
    add_route(ctx, "emergency-unavailable", r"^(?:110|112|911|999)$",
              [("respond", "403 Emergency calling unavailable"), ("hangup", "CALL_REJECTED")])
    add_route(ctx, "internal", r"^([12][0-9]{3})$",
              [("set", "call_timeout=30"), ("bridge", "user/$1@" + domain)])
    seen = set()
    for group in groups:
        if not isinstance(group, CallGroup) or group.extension in seen:
            raise ValueError("Invalid/duplicate call group")
        seen.add(group.extension)
        add_route(ctx, "ringgroup-" + group.extension, "^" + group.extension + "$",
                  [("bridge", ",".join("user/" + member + "@" + domain for member in group.members))])
    seen = set()
    for room in conference_numbers:
        check(room, ROOM, "conference extension")
        if room in seen:
            raise ValueError("Duplicate conference")
        seen.add(room)
        add_route(ctx, "conference-" + room, "^" + room + "$",
                  [("answer", ""), ("conference", room + "-" + domain + "@default")])
    if trunk is not None and trunk.enabled:
        digits = "|".join(re.escape(p) + "[0-9]{0," + str(15 - len(p)) + "}"
                          for p in trunk.allowed_prefixes)
        permission = fs_var("user_data(" + fs_var("sip_auth_username") +
                            "@" + domain + " var outbound_allowed)")
        add_route(ctx, "explicit-permitted-pstn", "^9((?:" + digits + "))$",
                  [("set", "outbound_redirect_fatal=true"),
                   ("bridge", "sofia/gateway/" + trunk.name + "/$1")], permission=permission)
    add_route(ctx, "default-deny", r"^.*$",
              [("respond", "403 No route permitted"), ("hangup", "CALL_REJECTED")])
    return xml(root)


def render_public_dialplan(domain: str, routes=()) -> str:
    check(domain, DOMAIN, "SIP realm")
    root = ET.Element("include")
    ctx = ET.SubElement(root, "context", name="famicom-provider-inbound")
    seen = set()
    for route in routes:
        if not isinstance(route, IncomingRoute) or route.did in seen:
            raise ValueError("Invalid/duplicate inbound route")
        seen.add(route.did)
        add_route(ctx, "inbound-" + route.extension,
                  "^" + re.escape(route.did) + "$",
                  [("bridge", "user/" + route.extension + "@" + domain)], authenticated=False)
    add_route(ctx, "reject-unknown-inbound", r"^.*$",
              [("respond", "404 Unknown DID"), ("hangup", "NO_ROUTE_DESTINATION")],
              authenticated=False)
    return xml(root)


def render_gateway(trunk: SipTrunk | None = None) -> str:
    root = ET.Element("include")
    if trunk is not None and trunk.enabled:
        gw = ET.SubElement(root, "gateway", name=trunk.name)
        for key, value in {
            "username": trunk.username,
            "password": trunk.password,
            "proxy": trunk.proxy,
            "realm": trunk.proxy,
            "register": "true",
            "register-transport": "tls",
            "caller-id-in-from": "false",
        }.items():
            ET.SubElement(gw, "param", name=key, value=value)
    return xml(root)

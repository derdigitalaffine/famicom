#!/usr/bin/env python3
"""Print only section/tag structure from FreeSWITCH's compiled XML.

DO NOT print any attribute/element content containing SIP A1 hashes, provider
passwords, extension credentials or other secrets. Pipe fsxml via stdin only.
"""
import sys
import xml.etree.ElementTree as ET

DOMAIN = "family.example.net"
payload = sys.stdin.buffer.read()
try:
    root = ET.fromstring(payload)
except ET.ParseError as exc:
    print("Compiled FreeSWITCH XML could not be parsed (redacted).")
    raise SystemExit(1) from exc


def walk(node, lineage=()):
    path = lineage + (node.tag,)
    if node.tag == "domain" and node.get("name") == DOMAIN:
        users = [user.get("id") for user in node.findall(".//user")]
        print("Domain XML path:", "/".join(path))
        print("Matching domain descendants:", len(users))
        print("Expected SIP user 1200 present:", "1200" in users)
    for child in node:
        walk(child, path)

print("Compiled XML root:", root.tag)
directories = [sec for sec in root.iter("section") if sec.get("name") == "directory"]
print("Directory sections:", len(directories))
for section in directories:
    print("Directory section child tags:", ",".join(child.tag for child in section)[:300])
walk(root)

if "--assert-directory" in sys.argv:
    active_domains = [d for sec in directories for d in sec.findall(".//domain") if d.get("name") == DOMAIN]
    if not active_domains or not any(d.find(".//user[@id='1200']") is not None for d in active_domains):
        raise SystemExit("No active canonical 1200 account in compiled directory section")
    print("Compiled FreeSWITCH directory acceptance: PASS")

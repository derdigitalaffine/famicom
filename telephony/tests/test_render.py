"""Negative security and XML contract tests; stdlib-only."""
import hashlib
import unittest
from xml.etree import ElementTree as ET

from telephony import (
    SipUser, SipTrunk, IncomingRoute, CallGroup, sip_ha1,
    render_directory, render_directory_response, render_dialplan,
    render_public_dialplan, render_gateway,
)

DOMAIN = "home.example.org"
PASS = "Many&SecretCharacters2026"


def user(extension="1001", role="adult", outbound=False):
    return SipUser("alice", extension, sip_ha1(extension, DOMAIN, PASS),
                   role=role, outbound_allowed=outbound)


def trunk(enabled=True, prefixes=("0049631",)):
    return SipTrunk("provider", "sip.provider.example", "account22",
                    "Long&ValidSecret2026", enabled=enabled,
                    allowed_prefixes=prefixes)


class TelephonyContracts(unittest.TestCase):
    def test_ha1_matches_digest_username_realm_password(self):
        expected = hashlib.md5(("1001:" + DOMAIN + ":" + PASS).encode()).hexdigest()
        self.assertEqual(sip_ha1("1001", DOMAIN, PASS), expected)

    def test_directory_no_plaintext_and_permissions_server_side(self):
        document = render_directory(DOMAIN, [user(), user("1002", outbound=True)])
        root = ET.fromstring(document)
        self.assertEqual(root.tag, "include")
        self.assertNotIn(PASS, document)
        self.assertEqual([u.find("./variables/variable[@name='outbound_allowed']").get("value")
                          for u in root.findall(".//user")], ["false", "true"])

    def test_xmlcurl_directory_envelope(self):
        document = ET.fromstring(render_directory_response(DOMAIN, [user()]))
        self.assertEqual(document.get("type"), "freeswitch/xml")
        self.assertEqual(document.find("section").get("name"), "directory")

    def test_disabled_and_duplicate_accounts(self):
        self.assertEqual(len(ET.fromstring(render_directory(DOMAIN, [
            SipUser("alice", "1001", sip_ha1("1001", DOMAIN, PASS), enabled=False)
        ])).findall(".//user")), 0)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            render_directory(DOMAIN, [user(), user()])

    def test_children_and_guests_cannot_have_paid_routes(self):
        for role in ("child", "guest"):
            with self.subTest(role=role):
                with self.assertRaises(ValueError):
                    user(role=role, outbound=True)

    def test_no_trunk_by_default_or_disabled(self):
        for t in (None, trunk(False)):
            document = render_dialplan(DOMAIN, trunk=t)
            self.assertNotIn("sofia/gateway", document)
            self.assertIn("default-deny", document)
            self.assertIn("sip_authorized", document)
            self.assertEqual(len(ET.fromstring(render_gateway(t))), 0)

    def test_narrow_egress_allowlist_mandatory(self):
        for prefixes in ((), ("0",), ("00",), ("0049", "0049"), ("090012345",),
                         ("013712345",), ("00123456",)):
            with self.subTest(prefixes=prefixes):
                with self.assertRaises(ValueError):
                    trunk(True, prefixes)

    def test_pstn_route_references_authenticated_user_permission(self):
        document = render_dialplan(DOMAIN, trunk=trunk())
        root = ET.fromstring(document)
        route = root.find(".//extension[@name='explicit-permitted-pstn']")
        self.assertIsNotNone(route)
        guards = [c.get("field") for c in route.findall("condition")]
        self.assertTrue(any("sip_authorized" in guard for guard in guards))
        self.assertTrue(any("sip_auth_username" in guard and "outbound_allowed" in guard
                            for guard in guards))
        self.assertIn("sofia/gateway/provider/$1", document)
        self.assertIn("0049631", document)

    def test_gateway_password_xml_escaped_and_disabled_empty(self):
        rendered = render_gateway(trunk())
        self.assertIn("&amp;", rendered)
        self.assertEqual(ET.fromstring(rendered).find(".//param[@name='password']").get("value"),
                         "Long&ValidSecret2026")

    def test_identifier_validation_rejects_dialplan_metacharacters(self):
        for domain in ("bad\"><action", "evil example.com",
                       "bad." + chr(36) + "{system(foo)}"):
            with self.subTest(domain=domain):
                with self.assertRaises(ValueError):
                    render_dialplan(domain)
        with self.assertRaises(ValueError):
            SipTrunk('gateway"><action', "sip.example.org", "account22",
                     "LongValidSecret2026", True, ("0049631",))

    def test_inbound_routing_has_no_escalation(self):
        document = render_public_dialplan(DOMAIN, [
            IncomingRoute("+496311234567", "1001")
        ])
        self.assertIn(r"\+496311234567", document)
        self.assertIn("user/1001@" + DOMAIN, document)
        self.assertNotIn("sofia/gateway", document)
        self.assertNotIn("XML default", document)
        self.assertIn("reject-unknown-inbound", document)

    def test_duplicate_did_forbidden(self):
        with self.assertRaises(ValueError):
            render_public_dialplan(DOMAIN, [
                IncomingRoute("00496311234567", "1001"),
                IncomingRoute("00496311234567", "1002"),
            ])

    def test_explicit_ringgroups_and_conferences(self):
        document = render_dialplan(DOMAIN,
                                   groups=[CallGroup("6000", ("1001", "1002"))],
                                   conference_numbers=("3000",))
        self.assertIn("user/1001@" + DOMAIN + ",user/1002@" + DOMAIN, document)
        self.assertIn("3000-" + DOMAIN + "@default", document)

    def test_group_and_conference_namespaces_are_disjoint(self):
        with self.assertRaises(ValueError):
            CallGroup("1001", ("1002",))
        with self.assertRaises(ValueError):
            CallGroup("6000", ("1001", "1001"))
        with self.assertRaises(ValueError):
            render_dialplan(DOMAIN, conference_numbers=["4000"])
        with self.assertRaises(ValueError):
            render_dialplan(DOMAIN, conference_numbers=["3000", "3000"])

    def test_unsupported_password_expansions_rejected(self):
        with self.assertRaises(ValueError):
            SipTrunk("provider", "sip.provider.example", "account22",
                     "Too" + chr(36) + "{secret}Long123", True, ("0049631",))


if __name__ == "__main__":
    unittest.main()

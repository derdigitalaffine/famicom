# FreeSWITCH: isolated routing and gateway renderer

This is a standalone, stdlib-only implementation slice of issue #3. **It does not deploy FreeSWITCH or activate provider calls.** The runtime API/Compose/Bootstrap work belongs to issue #2.

## Generated interfaces

| Function | Contract |
|---|---|
| `sip_ha1(extension, realm, password)` | Returns FreeSWITCH/SIP digest HA1; plaintext is transient |
| `render_directory(realm, users)` | `<include>` XML to load as directory data; extension equals SIP auth username |
| `render_directory_response(realm, users)` | `<document type="freeswitch/xml">` directory response for optional `mod_xml_curl` |
| `render_dialplan(realm, groups=(), conference_numbers=(), trunk=None)` | Isolated `famicom-internal` context, authenticated private calls, 6xxx ringing groups, 3xxx conferences; outbound disabled by default |
| `render_public_dialplan(realm, routes=())` | Isolated `famicom-provider-inbound` context, exact DID to internal extension, never arbitrary destination |
| `render_gateway(trunk=None)` | Empty configuration unless explicitly enabled; provider auth details must never enter Git or logs |

## Required runtime wiring

1. Canonical family identities and session/role rights must live in the Foundation API. Allocate SIP extensions only in 1000–2999, unique per account. Hash SIP passwords with HA1 at issuance and rotation; never store plaintext in generated directory files.
2. Set internal Sofia profile to `auth-calls=true` and `context=famicom-internal`. Use the dedicated provider Sofia profile with `context=famicom-provider-inbound`, a verified source-IP ACL, and restricted SIP trunk connection. Do **not** merge these routing contexts into stock `default` and `public` configs.
3. When a credential or permission changes, publish XML in a single atomic replacement with mode 0600 and reload FreeSWITCH configuration. Existing SIP registrations and live channels may survive XML reload; implement forced registration revocation and an active call policy separately.
4. PSTN calls require BOTH an explicit `enabled=True` SipTrunk and a per-user `outbound_allowed` directory permission from the authenticated identity. Dialing `9` + an allowlisted national/international number must not grant permissions by itself.
5. Native SIP should use VPN or verified SIPS/TLS and SRTP across untrusted networks. Browser telephone media requires WebRTC WSS and NAT/ICE/TURN verification. SIP signaling and media are distinct firewall concerns.
6. FreeSWITCH versions/images must be checked for `mod_sofia`, `mod_xml_curl` (if used), `mod_conference`, codec packages and external gateway TLS support before production.

## Critical limits

The generator validates the XML structure and the intended routing contract, not that a specific FreeSWITCH profile enforces the channel variable semantics. Confirm `sip_authorized` and `sip_auth_username` against the deployed Sofia version by integration tests. Provider-side caller ID enforcement, emergency calling, premium number restrictions, remote access, lawful recording, conferences and failover need separate service-provider-specific integration and security review.

**This application must not be advertised as emergency calling.** Outbound PSTN routing must be reviewed for toll-fraud exposure and should remain disabled until validated end to end.

## Tests

Run from repository root:

    python -m unittest discover -s telephony/tests -v

Tests cover failed permissions, XML escaping, isolated inbound routes, out-of-range extensions, duplicate accounts and forbidden/overly broad PSTN prefixes.
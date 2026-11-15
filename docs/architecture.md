# FamiCom – Architecture and Trust Boundaries

## Runtime
- **React + Mantine + Converse.js**: browser PWA / XMPP client. Browser calling uses SIP.js over Caddy-terminated WSS; native XMPP and SIP clients may connect independently.
- **FastAPI + SQLite**: canonical family identity, Argon2id password checks, HTTP-only sessions, roles, SIP secret issuance, audit. Administration never runs Docker commands.
- **Prosody 13**: XMPP (TCP/STARTTLS, WebSocket through Caddy, MUC, MAM, file sharing); `mod_auth_http` validates credentials against private API. No open user registration.
- **FreeSWITCH 1.10**: native SIP, bridge, dialplan, conferences, PBX; API atomically writes XML directory and gateway files into a shared volume and requests `reloadxml` over an internal password-authenticated event socket.
- **Caddy**: public HTTPS ingress, reverse proxies for `/api`, XMPP WebSocket, uploads and browser SIP-over-WebSocket; do not publish ESL.
- **TURN**: future opt-in coturn (not shipped in initial foundation); mobile/remote WebRTC media requires tested NAT/TURN configuration.

## Security invariants
- Server-side role checks; usernames constrained to ASCII alphanumeric/underscore with 3–32 characters; no case-colliding names; unique extensions.
- Session cookie never supplies the XMPP/SIP credential implicitly. Browser may prompt XMPP login separately; SIP credentials are returned only to that authenticated account on explicit request.
- XMPP HTTP auth API accessible only on Docker network, additionally Basic-authenticated; no reverse proxy route to internal auth.
- FreeSWITCH event socket remains on private Docker network with a randomly generated password, never published.
- Paid outbound calls **off by default**; child extensions are explicitly denied outbound bridge via server-side FreeSWITCH dialplan, adult/admin only; no SIP trunk credentials in Git and no unrestricted `0` route until an admin configures strict numeric prefix allow-lists.
- Bootstrap creates a 30-day self-signed native XMPP STARTTLS certificate in Docker secrets; native XMPP clients must explicitly trust it during evaluation and production requires a trusted cert. Test/self-signed TLS is NOT Internet-ready. ACME publicly trusted certificates, SIP/RTP firewall and NAT checks are deployment gates.
- A single database does not imply XMPP chat history/OMEMO key consistency: Prosody data volume and user device keys need coordinated backups.
- No emergency-calling guarantee; do not advertise this as an emergency phone replacement.

## Constraints and operational notes
- FreeSWITCH reference image is a community-build requiring amd64. Verify provenance and replace/pin image digest before production.
- For browser SIP, Caddy proxies `/sip-ws` to FreeSWITCH's plain internal WebSocket listener; only HTTPS is publicly accessible.
- Native SIP on 5060 is plaintext; bootstrap binds to loopback by default. Use WireGuard/Tailscale for remote native clients, or configure independently vetted SIPS/TLS.
- The initial slice is an integration foundation, not a claim that every FreeSWITCH feature, video/OMEMO/push pathway has passed end-to-end tests.

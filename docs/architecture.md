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

## Docker Compose file-backed secrets
Docker Compose mounts host files as read-only secrets; file-backed mounts do not enforce the Swarm `uid`/`gid`/`mode` attributes. The bootstrap keeps `.secrets/` at mode 0700 (no other host account may traverse it) and the individual files at mode 0644 so the API (uid 10001) and Prosody can read them via their private mounts. Do **not** place `.secrets/` in a world-traversable directory, expose host shell users access to it, or mount the secrets into any additional container. On deployments with higher threat requirements replace local file-backed secrets with an external secret manager or root-to-tmpfs injection. Never add the secret directory to Git.

## FreeSWITCH Event Socket and includes
Generated FreeSWITCH `X-PRE-PROCESS cmd="include"` directives resolve **relative to their containing XML file**; the bootstrap emits `default/*.xml` and `external/*.xml` (not doubled prefix paths). ESL is reachable only on the internal Docker network and uses a random password. The `localnet.auto` ACL permits the API's internal subnet to trigger config reloads; the event socket is never published on host ports. Operators running `fs_cli` must supply the generated ESL password (not the unsafe default).

## Asynchronous PBX readiness
Docker Compose reporting `started` does not imply that FreeSWITCH has loaded the Event Socket. Bootstrap now retries the private API-to-ESL handshake and initial directory reload; it fails visibly after bounded retries rather than silently leaving registered family accounts out of the PBX. The GitHub integration workflow checks authenticated `fs_cli` and API-driven `reloadxml` as separate paths.

The `localnet.auto` ESL ACL deliberately excludes the container's loopback interface. For authenticated `fs_cli` diagnostics from within the FreeSWITCH container, target `-H freeswitch` (its Docker service IP) so the source address belongs to the permitted local Docker subnet. This preserves the private ACL rather than broadening it just to make local diagnostics work.

## Hardened routing integration

The initial cleartext directory generator is now replaced by the canonical renderer in `telephony/render.py`. FreeSWITCH receives digest `a1-hash` credentials, unique 1xxx/2xxx SIP extensions, the isolated authenticated `famicom-internal` context, isolated `famicom-provider-inbound` context, and no public route to internal dialplan. The internal profile retains the unauthenticated `public` fallback context; documented FreeSWITCH behavior overrides it with the directory `user_context` **only after a successfully authenticated user call**. Premium and broad prefixes are rejected and outbound requires an explicit adult permission and a configured trunk. The API overwrites canonical XML atomically and deletes legacy cleartext directory files.

The first Foundation version issued three-digit extensions; the migration converts each such 2xx–9xx extension deterministically to 12xx–19xx (or a free 1xxx/2xxx extension on conflict). SIP clients must be updated to their new extension. Passwords are not changed. The production operator must restart FreeSWITCH and reconnect existing SIP endpoints; `reloadxml` alone does not revoke cached registrations or active channels.

### Consistent SIP digest realm
Because the family SIP secret is stored as an `a1-hash` and cannot be recomputed for a different challenge realm, the internal Sofia profile must set `challenge-realm`, `sip-domain`, `force-register-domain`, and `force-register-db-domain` to the canonical family domain. See [FreeSWITCH Sofia documentation](https://developer.signalwire.com/freeswitch/users-and-endpoints/sip-profiles/). The live SIP smoke explicitly fails if the server challenges for a different realm; arbitrary client-selected realms must never be trusted.

## Shared volume and process permissions
The API publishes SIP directory XML as owner-writable/group-readable files with mode `0640`. The API entrypoint ensures every generated directory is mode `0750`; the FreeSWITCH container joins supplemental GID 10001 solely for read-only access to those files (the PBX mounts remain read-only). This avoids publishing password-equivalent HA1 digests to world-readable files.

### Corrected group IDs and directory layout
The API image now pins **both UID and GID to 10001**, rather than relying on Linux `useradd --system` to assign a distro-dependent group. The FreeSWITCH service has supplemental group 10001. The stable `directory/default.xml` FreeSWITCH root follows the working bootstrap template; canonical HA1-rendered `<user>` entries are emitted exclusively under `directory/default/users.xml`. This avoids serializer-generated preprocessor formatting differences and preserves the 0640 security mode.

### Bootstrap CLI privilege boundary
Docker `compose exec` runs as the image user, **not the user to which the entrypoint later drops privileges**. Running API account initialization as container root had created root-owned, mode-0640 XML unreadable to the PBX. All provisioning CLI/smoke invocations now use `docker compose exec -T --user 10001:10001 api ...`. Integration also verifies non-root readability of the generated directory and the effective `user_exists` lookup.

### Canonical static user directory on FreeSWITCH
To avoid reload ambiguity with nested `X-PRE-PROCESS` includes, `provision.py` writes the complete rendered domain and its included enabled `<user>` nodes into `directory/default.xml` in one atomic replacement; legacy `directory/default/users.xml` is unlinked after publication. This is the same strict renderer verified by the standalone security contracts. Live integration asserts the active user lookup and non-root readability of that one file.

### Explicit FreeSWITCH master configuration
A live CI inspection identified that the bundled community image's effective `<section name="directory">` was empty even though the generated family domain XML existed, was readable and contained user 1200. FamiCom now binds a version-controlled `deploy/freeswitch/freeswitch.xml` master template. It explicitly loads the canonical `directory/default.xml` and the `dialplan/*.xml` tree, as well as unchanged module configuration, chatplan and English language resources, following the official FreeSWITCH vanilla configuration. The live check continues to assert that the compiled directory section contains the canonical 1200 user; **a file on disk alone does not mean FreeSWITCH has loaded the account**.

### FreeSWITCH XML include compatibility proven in CI
An isolated probe confirmed that FreeSWITCH was loading FamiCom's master XML while silently skipping the one-line API-rendered directory include. The API now uses `ET.indent` to publish multi-line, upstream-style `<include>` fragments without nested XML declarations. The probe has been removed. The live CI tests the compiled directory, verifies SHA/HA1-based SIP REGISTER for the initial admin, then provisions a second child account dynamically, checks the child cannot use the external trunk and registers that second account without a PBX restart.

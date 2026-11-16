# TURN / WebRTC NAT traversal

TURN is opt-in and does not imply reliable browser calling, media encryption verification, push notification support, or public SIP provisioning.

## Install and disable

1. Install FamiCom normally with `./scripts/bootstrap.sh` (TURN disabled).
2. Run `./scripts/turn-setup.sh enable`. Supply a DNS name (for example `turn.family.example.net`), a **bind IPv4** (default loopback) and the **public IPv4** that coturn should advertise when behind NAT.
3. After the browser has loaded over HTTPS and the family member logs in, `/api/telephony/ice` returns TURN URLs and per-user, one-hour HMAC/SHA-1 coturn REST credentials. The shared server secret never leaves Docker secret mounts. The API response uses `Cache-Control: private, no-store`.
4. For remote clients intentionally forward 3478 UDP + TCP and UDP 49160–49179. Provide real DNS and firewall rules and validate that a relay candidate is obtained *and* a two-device call has sound in both directions. Default `127.0.0.1` is safe but cannot serve other hosts.
5. Run `./scripts/turn-setup.sh disable` to stop coturn and stop issuing new ICE credentials. Already issued time-limited credentials are valid until expiration if the coturn service remains reachable.

## Security and topology

The optional Compose profile is `turn` using `coturn/coturn:4.18.0-r0`; default binds only to loopback and does not expose the event socket. The TURN shared secret is generated at initial setup as 32 random bytes represented in 64 lowercase hex characters, located in `.secrets/turn_rest`. Docker mounts the same file into the API and coturn containers; coturn materializes a temporary mode-0600 configuration in tmpfs (never writes the secret in command-line parameters). The relay port range is limited to 49160–49179/UDP. TURN is authenticated, with user and total allocation quotas and disabled loopback/multicast peers. It currently intentionally supports TURN UDP/TCP on 3478 without TURN over TLS 5349; HTTPS for the PWA does not protect the TURN TCP socket, while TURN's auth and WebRTC DTLS-SRTP protect their respective layers. For restrictive corporate networks, add verified TURN/TLS and do not claim 443-compatible connectivity.

This coturn relay does *not* automatically alter FreeSWITCH's external signaling or advertised SDP addresses. Configure SIP/RTP public IP, NAT routes, TLS/WSS, and real endpoints separately. On a production installation use a public DNS name and firewall segmentation; do not open the SIP 5060 port by default.

## Diagnose

- `docker compose --profile turn ps`
- `docker compose --profile turn logs --tail 80 turn` (avoid logging credentials)
- In the browser, check authenticated `/api/telephony/ice` but never copy temporary username/password to support tickets.
- Use the phone UI ICE diagnosis to inspect host/srflx/relay candidates and failure states without publishing IP addresses.
- Confirm connection to two real devices on distinct network types before claiming WAN media works.

Source: [coturn upstream reference](https://github.com/coturn/coturn/blob/master/README.turnserver).

## CI Live-Abnahme

Der Docker-Integrationstest startet den optionalen coturn-Container nur mit dem Loopback-Binding, aktiviert TURN in der API-Testumgebung, meldet sich als Test-Familienkonto über den HTTPS-Proxy an, holt temporäre ICE-Zugangsdaten und sendet einen echten TURN Allocate über UDP inklusive 401-Challenge/Nonce und Message-Integrity. Ein erfolgreicher Relay-Allocation-Test prüft das gemeinsame Geheimnis, den coturn-Start sowie den Authentifizierungsweg. Er ersetzt keinen echten Sprachtest zweier Endgeräte und garantiert keine WAN/NAT-Funktion.

### Non-root tmpfs permissions
The official coturn image runs as UID/GID 65534 (`nobody:nogroup`). The tmpfs containing the generated configuration is mounted with `uid=65534,gid=65534,mode=0700`; the configuration file itself remains mode `0600`. A root-owned 0700 mount is incompatible with this image and is caught by the live Compose TURN test.

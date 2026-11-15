# Roadmap

The canonical live priority and architecture discussion is [issue #1](https://github.com/derdigitalaffine/famicom/issues/1). This document captures release gates, not a second independent task board.

| Gate | Function | Exit criteria |
|---|---|---|
| G0 | Working scaffold | Compose config parse, Python tests, web build, CI checks |
| G1 | Accounts and XMPP | two separate accounts: login, chat, MUC, archives and file upload verified on Android, iOS and web |
| G2 | PBX | two native SIP clients and two browser clients call each other; hold, transfer, voicemail, conference, DTMF and call history exercised |
| G3 | Provider | trunk inbound/outbound with prefix controls, caller-ID policy, toll fraud fail-closed tests, bill monitoring |
| G4 | Collaboration | file handling limits, reactions, message search, read receipts, optional OMEMO cross-device verified |
| G5 | Family policy | delegated admins, child restrictions, privacy boundaries, recovery and data export |
| G6 | Production | external TLS, TURN, Android/iOS offline and push scenarios, disaster restore, performance/load and security review |

Unverified: native XMPP/Jingle interoperability with SIP; SIP.js video and group conferencing; proprietary WhatsApp interoperability (not part of scope); APNS/WebPush guaranteed background call ring; emergency dialing. Keep these explicitly visible until separately tested.

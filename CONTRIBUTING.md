# Contributing to FamiCom

Read [AGENTS.md](AGENTS.md) before code changes. Create a narrow issue referring to [roadmap #1](https://github.com/derdigitalaffine/famicom/issues/1), claim it with the exact v2 marker, work on a branch, run checks, and open a PR. Recheck collisions before merge.

Commit messages: `feat(scope): ...`, `fix(scope): ...`, `test(scope): ...`, `docs(scope): ...`. Include negative authorization tests for new endpoints, especially child account boundaries. Use conventional non-secret example values; never commit `.env`, secrets, cert private keys, exported chat content, SIP call logs, or recordings.

Keep the identity source of truth in the API, with XMPP and FreeSWITCH as adapters. Do not add a second account database without a roadmap decision. Server-side authorization is mandatory even if a frontend control is hidden.

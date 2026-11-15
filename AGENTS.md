# FamiCom Agent Orchestration Contract

Inspired by `familyos/AGENTS.md` and `familyos/docs/development/agent-coordination.md` (reviewed 2026-11-15). GitHub is the **only** shared planning and coordination plane.

## Authority
1. [#1](https://github.com/derdigitalaffine/famicom/issues/1): product roadmap, architectural gates, cross-issue dependencies.
2. One canonical work issue per bounded change: acceptance criteria, scope, claim, status.
3. One work branch + one PR: implementation, checks, review.
4. This file and `CONTRIBUTING.md`: workflow contract.

## Before edits
Read #1 and relevant issue/comments, then scan open `in progress` issues, open PRs, branches and touching files. Reuse canonical identity, XMPP, SIP and UI contracts. When another worker touches the same contract, comment and agree on interface/sequence **before** parallel modifications.

## Claim
Write exactly one structured comment to the work issue, using the literal marker:

```md
<!-- coordination:claim:v2 -->
## Work claim
- Worker: @username (human|agent|agent-assisted)
- Phase: discovery | implementation | review | blocked
- Scope: one bounded delivery
- Branch: feat/example | none
- PR: #123 | none
- Touches: concrete paths
- Coordination keys: domain:identity, api:accounts, ui:messenger | none
- Contracts changed: explicit or none
- Depends on: #... | none
- Parallel-safe with: explicit adjacent scope | none known
- Avoids / out of scope: ...
- Collision scan: open issues/PRs + #1 checked
```

Use `Phase: discovery` with no branch only while researching. Implementation must have a real branch; review must link the real PR. Do not create another claim for the same deliverable. Never force-push over another worker or merge with failing checks.

## Namespaced coordination keys
Use narrow identifiers: `domain:identity`, `domain:xmpp`, `domain:sip`, `api:users`, `api:telephony`, `ui:chat`, `ui:calls`, `policy:parental-controls`, `workflow:ci`. Semantic key collisions matter even without file overlaps.

## Exit/handoff
Use exactly `<!-- coordination:handoff:v2 -->` and record: Disposition (continue|superseded|paused|abandoned|completed), Successor, Branch/PR, Completed, Remaining, Decisions/invariants, Tests run, Risks, Suggested next work. Remove `in progress` on inactive/completed work. Do not mark complete until acceptance criteria/tests pass. PRs use `Refs #N` for partial slices or a standalone `Closes #N` only on full completion.

## Security architecture gates
- No common or demo SIP passwords, exposed FreeSWITCH event socket, plaintext web auth, automatic paid-call trunk activation, hardcoded credentials, or XMPP open registration.
- Children and guests must not gain admin/trunk access through frontend-only checks.
- Document a tested rollback, data persistence, certificate lifecycle and SIP toll-fraud controls before claiming production readiness.
- An AI agent never acts as a runtime caller, admin, or family member; AI coordination governs code changes only.

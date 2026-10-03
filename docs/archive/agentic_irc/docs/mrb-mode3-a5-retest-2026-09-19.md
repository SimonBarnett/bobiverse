<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mrb-mode3-a5-retest-2026-09-19.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - Mode 3 A5 live retest (2026-09-19)

**Repo:** SimonBarnett/agentic_irc
**Tip:** 4abdce5 fix: Mode 3 Schannel handshake and CAP END; A5 IONOS live smoke
**Prior:** mrb-mode3-2026-09-19.md PASS-with-nits (A5 open)
**Job:** ionos 325993ce
**Evidence:** docs/mode3-live-smoke-2026-09-19.md

## Verdict

**PASS - ready for human UAT** of Mode 3 thin moot CLI on **Windows 8 / Server 2012+ Schannel** (proven here on Server 2022 IONOS).

**Does not** claim Windows 95/98/NT4/XP live Libera. U1 remains blocked for those rows.

## A5 gate (closed)

| Criterion | Evidence |
|---|---|
| Chair OPEN moot | cm-bob moot 4a9a915e3a97b319 on #cm-bob-oscar |
| Thin JOIN roster | cm-bob, cm-thin on disk roster |
| Operators allowlist | --operators cm-bob; floor not required |
| Sealed exec hostname | job d4ff0b48526526ed |
| Stdout to chair | WIN-MPRE8VI4U6U in dumb/results JSON |
| Secrets | PSK off-channel; not committed |

## Bugs found in live path (fixed in 4abdce5)

1. Schannel incomplete handshake / client-cert optional request handling.
2. CAP LS without CAP END blocked numeric 001.

Offline: airc-moot-thin --selftest ok; tests/test_moot_thin_proto.py 16 passed.

## Nits (non-blocking for UAT phrase)

1. **Rolling release lag.** Published mode3-thin 0.1.0 still failed handshake before this fix. Operators must use a build from 4abdce5+ (or wait for next green mode3-thin-release on src/moot_thin/**). Prefer bump VERSION if immutable tag should not look like the broken 0.1.0.
2. Libera 3-connection cap: spider briefly paused - document in MANUAL if not already.

## Pass bar vs first Mode 3 MRB

| Gate | Now |
|---|---|
| A1-A4 | Still pass |
| A5 IONOS live smoke | **Pass** |
| A6 Bob UAT phrase | **Granted** for Win8+ Schannel Mode 3 only |

## Non-claims

- Win95 TLS
- Phase 5 Server 2012 live (separate WP-P5 live smoke still open)
- AGPK-mode dumb / YIELD* backlog items

## Sign-off

Bob hostile MRB - 2026-09-19 Europe/London - tip 4abdce5 - **ready for human UAT** (Mode 3, modern Windows Schannel).

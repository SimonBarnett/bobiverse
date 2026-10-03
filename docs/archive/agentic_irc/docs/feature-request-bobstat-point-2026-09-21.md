<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bobstat-point-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: BOB v1 POINT / bobstat (park landed code)

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**Intake issue:** https://github.com/SimonBarnett/agentic_irc/issues/8  
**Prior FAIL board:** https://github.com/SimonBarnett/agentic_irc/issues/5 (blocker 1 — code on `main` without FR)  
**Raised by:** Simon (missing-features walk of `273ae1a` / quiet-talk #6)  
**Hostile MRB chair:** Bob (issue #8; do not stamp human UAT from this park)

Implementation landed on `main` at `adcf6b7` (*bobstat: BOB v1 POINT schema for the #bobiverse MODE2 free moot*) before this markdown existed. This document **parks** that behaviour; it is not a request to add new wire fields in the same MRB pass. Conversational `#bobiverse` talk is **#6** / agentic_build#36, not this FR.

## Problem

Fleet boxes need a compact, **cleartext** status line on the MODE2 **free** `#bobiverse` moot so peers and tooling can refresh `bob-peers/<id>.json` without SEAL or secrets. The parser, `irc_agent` ingest, and pytest gate existed without a dated MUST/MUST NOT doc — Bob MRB #5 **FAIL** on that gap alone.

## LOCKED

1. **MODE2 free only.** `BOB v1` rides `MOOT v1 POINT` trailing text. Not SEAL. Not a secret channel.
2. **MUST NOT** put secrets on the POINT line (`password=`, `XAI_API_KEY=`, connect files, PSK, PIN).
3. **Max 350 characters** on the formatted line. If truncated, the formatter ends with `-` (lossy; builders should trim jobs list).
4. **`bob-peers/<id>.json`** under `AGENTIC_IRC_HOME` is cleartext cache, not a seal. Do not commit live home dirs; repo `.gitignore` does not need agent home trees.
5. **Do not break** prior POINT readers in one jump. Extend only via a later FR + MRB.
6. **Machine `id=`** must match `^[a-z0-9][a-z0-9-]{0,62}$` (lowercase DNS-like slug). Uppercase or invalid ids are rejected (`id=NOPE` is intentionally invalid in tests).

## Wire (v1)

Trailing text of `MOOT v1 POINT <moot_id> :<text>` (see `scripts/bobstat.py`):

```text
BOB v1 id=<machine> weekly=<0-100|-> running=<n> queued=<n> lastSeen=<iso8601|-> jobs=<-|repo:state,...>
```

- `weekly`: that machine's Grok weekly remaining percent, or `-` if unknown.
- `jobs`: `-` or comma-separated `owner/repo:state` tokens (no spaces). Malformed job tokens are dropped on parse, not fatal.
- `irc_agent` writes peer json when incoming POINT text parses.

## UNKNOWN

- Live Ergo `#bobiverse` POINT cadence vs tray-only disk refresh (producer dedupe is agentic_build#14).
- Operator playbook when `jobs=` does not fit in 350 chars (priority order not locked).
- Threat model paragraph vs `docs/mode3-zero-config-2026-09-19.md` (who/when/size already leak; weekly/running/queued/jobs add fleet detail). Accept as product choice once FR exists; no human UAT claim here.

## Gap vs current tree (2026-09-21 @ `main`)

| Item | Status |
|---|---|
| `scripts/bobstat.py` parse/format/peers | **Present** since `adcf6b7` |
| `scripts/irc_agent.py` POINT → `write_peer` | **Present** |
| `tests/test_bobstat.py` offline gate | **Present** |
| This FR markdown | **This commit** (closes MRB #5 blocker 1) |
| `docs/build-and-test-plan-bobstat-point-2026-09-21.md` | **This commit** |
| README link to FR + id rule | **This commit** |
| New BOB v1 fields / quiet-talk English | **Out of scope** (#6 / separate FR) |
| Live POINT on Ergo / two-nick Libera 001 | **Not required** for this park; CI stays offline |

## Acceptance (issue #8)

1. Issue #8 and this markdown exist on the default branch path via merged PR (MRB home for bobstat).
2. Wire stays compatible with today's `BOB v1 id= weekly= running= queued= lastSeen= jobs=` readers unless a later FR extends them.
3. `tests/test_bobstat.py` remains the off-DEV gate; CI must not open IRC.

## Non-goals

- Implementing quiet-talk DMs, `!bobiverse`, or removing channel POINT (#6).
- Declaring ready for human UAT for bobstat, multi-agent (#3), DUMB ergonomics (#2), or Mode 3 visibility (#4).
- Writing `docs/mrb-*.pdf` for this board.

## Related

- Quiet talk FR: `docs/feature-request-bobiverse-quiet-talk-2026-09-20.md` / issue #6  
- Build plan: `docs/build-and-test-plan-bobstat-point-2026-09-21.md`

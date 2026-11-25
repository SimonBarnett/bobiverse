# Digest go-gate vs hold vs Depends-on CLOSED

**BOB-G2 / FR #8838** + **BOB-G3 / FR #9108** Digest flag. Chair short note.
Cites Plan playbook **VIS-G3** / **VIS-G1** and product encoding **BOB-G1**
(`bob_g1_skip_held_digest`) + **BOB-G3** (`digest_issue_reason`).

Three different gates. Do not collapse them.

## Digest flag (BOB-G3)

| | |
|---|---|
| Signals | Label `digest` or `fr-digest` (case-insensitive; string/dict/CSV), or line-anchored body `Kind: digest` / `Kind: fr-digest` (plain or bold). **Never the title alone.** |
| Scope | Issues / FR rows only. MRB and PR-shaped rows are never digests. Never stamp these labels on PRs (filer strips them). |
| Dispatch | Digests are **gate records**: never offered and never `!assign`ed as work. They stay in the queue. `!list` shows `[digest]`. |

## 1. Digests go-gate (`digest`/`fr-digest` + `hold`)

| | |
|---|---|
| What | One **digest** issue per target repo parks a batch. Labels: `digest`/`fr-digest` and `hold`. Children stamp `Depends-on: #digest` (plus any intra-batch Depends-on). |
| Release | **Unhold alone** (remove `hold`). Digest may stay OPEN. Close is optional. |
| Offer path | BOB-G1: depend with `hold` -> skip reason `depends-held` (`bob_g1_skip_held_digest`). Unheld digest -> `ok-fr-digest` while still OPEN (does not trip depends-open). |
| Shared gate | **FR #9455** `depends_gate_reason` / `bob_g1_shared_gate` — offer, `!assign`, and stuck/report use **one** helper. Digests absent from the local queue still resolve via `issue_fetch` (FR #9418 / #9434). |
| Plan | VIS-G3: visionary skill parks the digest with those labels; children are not assignable until unhold. |
| Monitor | `fr_digest` (FR #8849): EXIT 1 when an offered/accepted child still Depends-on a local held digest row. |

## 2. Hold (issues-only)

| | |
|---|---|
| What | Label `hold` / `on-hold` on an **issue/FR** (never on a PR — FR #9082). Also `HOLD:` body stamps. |
| Effect | Blocks **that** FR from offer (FR #4009 `row_fr_hold_reason`). Does not by itself mean "digest go-gate". **FR #9402:** labeling `hold` (webhook) also drops the unaccepted row and clears `offered_to` / seat-holds so an idle seat is not stuck `busy (offered FR …)`. Digests stay queued (BOB-G3). |
| Distinct | A lone `hold` without Digest flag is not the digest check. Ops watchers that only look for `hold` are not VIS-G3 / BOB-G1. Ops/MONITORING rebuild-install trackers are skip_fr `ops_monitor_tracker` (not feature-request shop work) — see `monitoring.md` FR #9402. |

## 3. Depends-on CLOSED (ordinary backlog)

| | |
|---|---|
| What | Issue body `Depends-on: #N` (or `owner/repo#N`). Ordinary parent FRs must be **CLOSED** before the child is offerable. |
| Effect | BOB-D3 / FR #8754 / FR #8807: open depend -> skip (`depends-open` / `bob_d3_skip_open`). |
| Exception | Unheld digests are allowed OPEN (BOB-G1 `ok-fr-digest`). Held digests use gate 1 (`depends-held`), not this CLOSED rule. |
| Monitor | `depends_on` (FR #8848): EXIT 1 when an offered/accepted row still Depends-on an OPEN local queue row (chair missed BOB-D3). |

## Quick map

```
hold label alone                 -> block that FR (issues-only)
digest/fr-digest (+ optional Kind:) -> never dispatch as work; gate record
digest/fr-digest + hold          -> block children until unhold (close optional)
Depends-on ordinary OPEN         -> block until parent CLOSED
Depends-on unheld digest OPEN    -> offer OK (BOB-G1)
tip-priority sibling (held)      -> LIST ONLY on digest; no Depends-on (FR #9854)
```

Architecture (theme LOCKED): `hold label | fr-digest Depends-on | parent CLOSED Depends-on`.

## Tip-priority siblings (LIST ONLY) — FR #9854

Digest body has **two** child sections while held:

| Section | Child body | Offer while digest held |
|---|---|---|
| **Tip-priority siblings (LIST ONLY)** | **No** `Depends-on: #<digest>` | Offerable (tip merge FIX/MRB must not starve) |
| **Children (Depends-on this digest)** | Plain `Depends-on: #<digest>` | Skipped (`depends-held` / #9821) |

Use tip-priority for tip-blocking work (e.g. main/tip `build-jeeves` red FIX) that must merge **before** the held lessons digest unholds. Still **list** those issues on the digest so the batch is visible; never wire `Depends-on` onto them while `hold` remains. Helpers: `fr_digest_gate.stamp_digest_depends_on(digest_held=..., tip_priority=...)` and section markers `TIP_PRIORITY_SECTION` / `CHILDREN_SECTION`. After unhold, tip-priority rows may take Depends-on like parked children if desired.

Fail-when: MONITORING / harvest auto-stamps `Depends-on: #<held-digest>` on a tip-blocking FIX → held-digest gate starves the tip merge (class of #9840 cleared by Haiku).

## Related

- Index: `bob/docs/fr-index-fr-digest-go-gate-2026-11-21.md` (docs branch park)
- BOB-G1 offer path: FR #8837 / `bob_g1_skip_held_digest`
- FR #9418 / #9420: live digest when go-gate row absent from queue
- FR #9434 / #9444: stuck/report + Depends-on annotations share `issue_fetch`
- FR #9455: `depends_gate_reason` (`bob_g1_shared_gate`) — offer = assign = stuck
- FR #9854: tip-blocking FIX list-only (no Depends-on while digest held)
- VIS-G3 Plan skill: SimonBarnett/skills-visionary VIS-G3
- BOB-G3 Digest flag recognition: FR #9108
- Product Depends-on vs hold docs theme (BOB-D8 #8812) is the D* track; this note is the G* digest go-gate track

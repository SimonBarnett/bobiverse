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
| What | One digest issue per target repo parks a batch. Children stamp `Depends-on: #digest`. |
| Release | **Unhold alone** (remove `hold`). Digest may stay OPEN. Close is optional. |
| Offer path | BOB-G1: depend with `hold` -> `depends-held`. Unheld digest -> `ok-fr-digest` while OPEN. |
| Monitor | `fr_digest` (FR #8849): EXIT 1 when offered/accepted child Depends-on a held digest. |

## 2. Hold (issues-only)

| | |
|---|---|
| What | Label `hold` / `on-hold` on an issue/FR (never on a PR for the issues-only pair — FR #9082). |
| Effect | Blocks **that** FR from offer. A lone `hold` without Digest flag is not the digest check. |

## 3. Depends-on CLOSED (ordinary backlog)

| | |
|---|---|
| What | Ordinary parent FRs must be **CLOSED** before the child is offerable. |
| Exception | Unheld digests are allowed OPEN (BOB-G1/G3). |

## Quick map

```
hold label alone                 -> block that FR
digest/fr-digest (+ optional Kind:) -> never dispatch as work; gate record
digest/fr-digest + hold          -> block children until unhold
Depends-on ordinary OPEN         -> block until parent CLOSED
Depends-on unheld digest OPEN    -> offer OK
```

---
name: bobiverse-jeeves-agent-depends-on
description: >
  Jeeves / MONITORING playbook for Depends-on preconditions (BOB-D*): parse
  Depends-on from issue bodies, treat hold vs Depends-on CLOSED as distinct
  gates, and report when the chair offers or accepts a row while a depend is
  still OPEN. Use when Depends-on, hold of dependencies, skip-until-closed,
  BOB-D1..D9, #8754, or /bobiverse-jeeves-agent-depends-on. When BOB-D is live,
  every monitor cycle runs this node.
depends_on:
  - bobiverse-jeeves-monitor
---

# bobiverse-jeeves-agent-depends-on

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Theme index: BOB-D1..D9 (#8805-#8813). Vision packs under `bob/docs/feature-request-depends-on-*-2026-11-21.md` on branch `docs/depends-on-jeeves-frs-2026-11-21`. Omnibus backlog-id Depends-on (#8754) is superseded by issue# refs; BOB-D9 closes/retargets it after D1-D8.

## Three gates (net result, confirmed)

| Gate | Mechanism | Who owns product |
|---|---|---|
| 1 | GitHub label `hold` (manual park) | operators / Plan |
| 2 | Body line `Depends-on:` — every listed issue must be **CLOSED** before offer | BOB-D* chair |
| 3 | `fr-digest` go-gate (unhold releases) | BOB-G* — see `bobiverse-jeeves-agent-fr-digest` |

This skill owns **gate 2** (and how it differs from gate 1). Do not confuse `hold` with Depends-on CLOSED.

## Grammar (LOCKED)

- `Depends-on: #N` — same repo as the FR
- `Depends-on: owner/repo#N` — cross-repo
- `Depends-on: (none)` — empty / no deps
- Multiple refs: comma or whitespace separated on one line (implementer follows D1 parse)
- Distinct from legacy backlog ids (`BOB-33`) in #8754 — those are not this grammar

## When live (monitor cycle)

After token-free checks, if BOB-D offer skip is deployed (chair stamps `depends-open` / `fr_hold_reason` class, or `Test-JeevesMonitorDependsOn` exists):

1. Scan live digest + queue for **accepted or offered** rows whose issue body still has an OPEN Depends-on ref.
2. EXIT 1 / intake when the chair offered or accepted despite OPEN depends (product miss). De-dup against #8807 / #8754.
3. Rows correctly skipped with reason `depends-open` are **not** starve — do not file empty-queue / idle+ungated for them.
4. `hold` alone without Depends-on is gate 1 — leave parked; do not treat as Depends-on bug.
5. Prefer deterministic script when present: `Invoke-JeevesMonitorCheck.ps1 -Check depends_on` (FR filed with this skill). Until the script lands, use `gh issue view` on offered ids + body parse (ASCII).
6. CAST IRON point 5: when the Depends-on monitor playbook is proven, FR the durable check into the token-less chair (`tools\monitor\depends_on.py` + wrapper + chair skip stamps) so it runs without an LLM.

## Until BOB-D is live

- Skills and FRs may be on `hold`. Do not remove hold or chase D* as delays.
- Still teach operators the grammar; still comment on #8754 / D* when backlog-id Depends-on confuses seats.
- Do not invent chair parse behaviour that is not on tip.

## Hard rules

- No secrets. Public hosts only (`bob.ntsa.uk`, `irc.ntsa.uk`, `github.com`).
- Never edit `queue.json` / ledger / digest by hand.
- No `!assign` / `!focus` / fake ACK/DONE unless FR #8827 (monitor full Jeeves commands) is live **and** the action is keep-queue-moving (e.g. `!ignore` a held FR already accepted). Prefer intake first.
- Off chair: public digest + `gh` only; no chair-local false findings (FR #8579).

## Output (required when this node runs)

| job | depend | depend state | chair action | ok? | evidence | existing issue |
|---|---|---|---|---|---|---|

- **ok?** — `yes` if skipped while OPEN or offered only when all CLOSED; `no` if offered/accepted while OPEN.
- Empty table with `no Depends-on rows in flight` is valid.

## Refs

- Index: #8805 body / `fr-index-depends-on-jeeves-2026-11-21.md`
- D3 skip-open: #8807
- D8 docs vs hold: #8812
- Sibling digest gate: `bobiverse-jeeves-agent-fr-digest`
- Live MONITORING loop: `bobiverse-jeeves-monitor`, `monitor-start`

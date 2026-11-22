---
name: bobiverse-jeeves-agent-depends-on
description: >
  Jeeves / MONITORING playbook for Depends-on preconditions (BOB-D*): parse
  Depends-on from issue bodies, treat hold vs Depends-on CLOSED as distinct
  gates, and report when the chair offers or accepts a row while a depend is
  still OPEN. Token-free check `depends_on` (FR #8848). Use when Depends-on,
  hold of dependencies, skip-until-closed, BOB-D1..D9, #8754, or
  /bobiverse-jeeves-agent-depends-on. When BOB-D is live, every monitor cycle
  runs this node.
depends_on:
  - bobiverse-jeeves-monitor
---

# bobiverse-jeeves-agent-depends-on (FR #8848)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Theme index: BOB-D1..D9 (#8805-#8813). Vision packs under `bob/docs/feature-request-depends-on-*-2026-11-21.md` on branch `docs/depends-on-jeeves-frs-2026-11-21`. Omnibus backlog-id Depends-on (#8754) is superseded by issue# refs; BOB-D9 closes/retargets it after D1-D8.

Token-free. Distinct from the hold / HOLD label and from the `fr_digest` check.

## Three gates (net result, confirmed)

| Gate | Mechanism | Who owns product |
|---|---|---|
| 1 | GitHub label `hold` (manual park) | operators / Plan |
| 2 | Body line `Depends-on:` - every listed issue must be **CLOSED** before offer | BOB-D* chair |
| 3 | `fr-digest` go-gate (unhold releases) | BOB-G* - see `bobiverse-jeeves-agent-fr-digest` |

This skill owns **gate 2** (and how it differs from gate 1). Do not confuse `hold` with Depends-on CLOSED.

## Grammar (LOCKED)

- `Depends-on: #N` - same repo as the FR
- `Depends-on: owner/repo#N` - cross-repo
- `Depends-on: (none)` - empty / no deps
- Multiple refs: comma or whitespace separated on one line (implementer follows D1 parse)
- Distinct from legacy backlog ids (`BOB-33`) in #8754 - those are not this grammar

## Token-free check (FR #8848)

`scripts\Test-JeevesMonitorDependsOn.ps1` or `Invoke-JeevesMonitorCheck.ps1 -Check depends_on`.

Python: `tools\monitor\depends_on.py`. Exit 0 ok, 1 finding, 2 error. One JSON line. No GitHub token.

| Situation | Exit |
|---|---|
| Offered or accepted row, body `Depends-on:` ref still OPEN in this queue | 1 |
| Same refs but the row is skipped (`status=skipped`, `depends_skipped`, or `skip_reason`) | 0 |
| No Depends-on rows, or queue file missing | 0 (`soft_ok=no_depends_on_rows`) |
| Live homes and BOB-D skip/parse is not on this tip | 0 (`soft_ok=product_not_on_tip`) |

OPEN means the ref is in `unaccepted`, `offered`, or `accepted` on the local queue. A ref that is not in the queue is unknown (no token, no alarm). A skipped row is not a miss.

Live runs (no `--chair-home`) stay soft-ok until either:

* `common/scripts/depends_on_parse.py` exists, or
* `common/scripts/gitclaim.py` contains `bob_d3_skip_open`

Fixture runs pass `--chair-home` and always evaluate the queue. BOB-D3 (skip offer while a depend is OPEN) should add that marker when it lands so this check starts reporting real misses.

## When live (monitor cycle)

After token-free checks, if BOB-D offer skip is deployed (chair stamps `depends-open` / `fr_hold_reason` class) or the FR #8848 script is present:

1. Run `Invoke-JeevesMonitorCheck.ps1 -Check depends_on` (or `Test-JeevesMonitorDependsOn.ps1`).
2. EXIT 1 / intake when the chair offered or accepted despite OPEN depends (product miss). De-dup against #8807 / #8754 / #8848.
3. Rows correctly skipped with reason `depends-open` are **not** starve - do not file empty-queue / idle+ungated for them.
4. `hold` alone without Depends-on is gate 1 - leave parked; do not treat as Depends-on bug.
5. CAST IRON point 5: durable check lives in `tools\monitor\depends_on.py` + wrapper; chair skip stamps still land via BOB-D3.

## Until BOB-D is live

- Skills and FRs may be on `hold`. Do not remove hold or chase D* as delays.
- Still teach operators the grammar; still comment on #8754 / D* when backlog-id Depends-on confuses seats.
- Soft-ok `product_not_on_tip` until parse/skip markers exist; do not invent chair parse behaviour that is not on tip.

## Hard rules

- No secrets. Public hosts only (`bob.ntsa.uk`, `irc.ntsa.uk`, `github.com`).
- Never edit `queue.json` / ledger / digest by hand.
- No `!assign` / `!focus` / fake ACK/DONE unless FR #8827 (monitor full Jeeves commands) is live **and** the action is keep-queue-moving (e.g. `!ignore` a held FR already accepted). Prefer intake first.
- Off chair: public digest + `gh` only; no chair-local false findings (FR #8579).

## Output (required when this node runs)

| job | depend | depend state | chair action | ok? | evidence | existing issue |
|---|---|---|---|---|---|---|

- **ok?** - `yes` if skipped while OPEN or offered only when all CLOSED; `no` if offered/accepted while OPEN.
- Empty table with `no Depends-on rows in flight` is valid.

## Wire

Every monitor cycle once BOB-D is live: `monitor-start` and `bobiverse-jeeves-monitor` list `depends_on`. Report exit 1 via intake. Do not edit the queue and do not act as chair.

## Refs

- Index: #8805 body / `fr-index-depends-on-jeeves-2026-11-21.md`
- D3 skip-open: #8807
- D8 docs vs hold: #8812
- Monitor check: #8848
- Sibling digest gate: `bobiverse-jeeves-agent-fr-digest`
- Live MONITORING loop: `bobiverse-jeeves-monitor`, `monitor-start`

---
name: bobiverse-jeeves-agent-depends-on
description: >
  Token-free Jeeves monitor check for offered or accepted queue rows whose
  Depends-on refs are still OPEN (chair missed BOB-D3). Run every monitor
  cycle once BOB-D is live. Use with monitor-start / bobiverse-jeeves-monitor.
---

# bobiverse-jeeves-agent-depends-on (FR #8848)

Token-free. Distinct from the hold / HOLD label and from the `fr_digest` check.

## Check

`scripts\Test-JeevesMonitorDependsOn.ps1` or `Invoke-JeevesMonitorCheck.ps1 -Check depends_on`.

Python: `tools\monitor\depends_on.py`. Exit 0 ok, 1 finding, 2 error. One JSON line.

| Situation | Exit |
|---|---|
| Offered or accepted row, body `Depends-on:` ref still OPEN in this queue | 1 |
| Same refs but the row is skipped (`status=skipped`, `depends_skipped`, or `skip_reason`) | 0 |
| No Depends-on rows, or queue file missing | 0 (`soft_ok=no_depends_on_rows`) |
| Live homes and BOB-D skip/parse is not on this tip | 0 (`soft_ok=product_not_on_tip`) |

Grammar: `Depends-on: #N` (same repo as the row), `owner/repo#N`, or `(none)`.

OPEN means the ref is in `unaccepted`, `offered`, or `accepted` on the local queue. A ref that is not in the queue is unknown (no token, no alarm). A skipped row is not a miss.

## Product on tip

Live runs (no `--chair-home`) stay soft-ok until either:

* `common/scripts/depends_on_parse.py` exists, or
* `common/scripts/gitclaim.py` contains `bob_d3_skip_open`

Fixture runs pass `--chair-home` and always evaluate the queue. BOB-D3 (skip offer while a depend is OPEN) should add that marker when it lands so this check starts reporting real misses.

## Wire

Every monitor cycle once BOB-D is live: `monitor-start` and `bobiverse-jeeves-monitor` list `depends_on`. Report exit 1 via intake. Do not edit the queue and do not act as chair.

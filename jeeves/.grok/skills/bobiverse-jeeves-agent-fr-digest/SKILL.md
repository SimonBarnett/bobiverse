---
name: bobiverse-jeeves-agent-fr-digest
description: >
  Token-free Jeeves monitor check for a child FR offered or accepted while its
  Depends-on digest issue still has labels fr-digest and hold (missed BOB-G1).
  Run every monitor cycle after depends_on once BOB-G is live.
---

# bobiverse-jeeves-agent-fr-digest (FR #8849)

Token-free. Distinct from `depends_on` (OPEN issue refs) and from a lone hold label.

## Check

`scripts\Test-JeevesMonitorFrDigest.ps1` or `Invoke-JeevesMonitorCheck.ps1 -Check fr_digest`.

Python: `tools\monitor\fr_digest.py`. Exit 0 ok, 1 finding, 2 error. One JSON line.

| Situation | Exit |
|---|---|
| Offered or accepted child, `Depends-on:` row has labels `fr-digest` and `hold` | 1 |
| Same child after unhold (digest keeps `fr-digest`, `hold` is gone) | 0 |
| Depend not in the local queue | 0 (unknown, no token) |
| Live homes and BOB-G gate is not on this tip | 0 (`soft_ok=product_not_on_tip`) |

Grammar: `Depends-on: #N` uses the child row repo; `owner/repo#N` is explicit.

## Product on tip

Live runs (no `--chair-home`) stay soft-ok until either:

* `common/scripts/fr_digest_gate.py` exists, or
* `common/scripts/gitclaim.py` contains `bob_g1_skip_held_digest`

Fixture runs pass `--chair-home`. BOB-G1 should add that marker when the offer path starts skipping held digests.

## Wire

Every monitor cycle after `depends_on`, once BOB-G is live. `monitor-start` lists `fr_digest`. Report exit 1 via intake. Do not edit the queue.

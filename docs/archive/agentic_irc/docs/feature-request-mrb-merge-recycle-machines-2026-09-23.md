<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-mrb-merge-recycle-machines-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: MRB-to-main must recycle running machines

https://github.com/SimonBarnett/agentic_irc/issues/168

Simon 2026-09-23: changes to this repo and `agentic_build` must be clearly
marked so anyone merging to `main` is responsible for recycling the
running machines, and if required notifying ionos to restart IRC
altogether.

## Objective

After a PASS-nits merge to `agentic_irc` or `agentic_build` `main`, the
live fleet is recycled (or ionos is told to restart IRC) so boxes are
not left on the old tree.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Recycle duty written in owner skills | `bob-hostile-mrb` + `agentic-irc` / `bob-irc` name recycle-after-merge | `rg` those skills for recycle + ionos restart | skill silent on merge-to-main recycle |
| S2 | Test-Pack / pytest asserts the duty | at least one assertion on skill or README text | `tools/Test-Pack.ps1` (build) or `pytest` (irc) | pack green while skills omit recycle |
| S3 | No live recycle from the implementer PR | docs only; no `!recycle` from workers | PR body + skill "Bob/ionos recycle, not worker" | worker script calls live recycle |

## Shape

Primary: service

Hybrid note: docs/skills on the existing IRC + fleet services. No new UI.

LOCKED

## Stack

Default: existing `agentic_irc` Python + `agentic_build` PowerShell skills.

Why: the duty belongs where MRB merge and Watch-Bobiverse already live.

Why-not: a new service or webhook — UNKNOWN transport; do not invent.

LOCKED

## Architecture

```
MRB PASS-nits merge main
        |
        v
skill text: merger recycles Watch-Bobiverse / tray / seats
        |
        +-- ionos: restart IRC / chair if the change needs it
        |
        v
live boxes pull + recycle (not the implementer from DEV1)
```

LOCKED

## Screens

No UI. Mocks are placeholders so the vision gate can run (no PNG).

| id | file | state |
|----|------|-------|
| M1 | docs/mocks/mrb-merge-recycle/home.html | primary |
| M2 | docs/mocks/mrb-merge-recycle/empty.html | empty |
| M3 | docs/mocks/mrb-merge-recycle/error.html | error |

## Gap vs current tree

`eee0bd0` (`origin/main`): MRB skills say merge/close/pull. They do not
LOCK that the human/Bob who merges must recycle running machines or
tell ionos to restart IRC. `!recycle` (Jeeves #152) is a command, not
this duty text.

## LOCKED

1. Mark `agentic_irc` and `agentic_build` so merge-to-main owners recycle
   live machines.
2. If the change needs it, notify ionos to restart IRC altogether.
3. Workers do not live-recycle flamingo from another box.
4. Harvest as PR, not commit to main. No UAT.

## UNKNOWN

- Exact recycle sequence per change class (tray only vs full IRC).
- Whether Jeeves `!recycle` is the ionos notify path (see #152).
- #167 shop-only spam is a separate FR.

## Acceptance

| ID | Gate |
|----|------|
| A1 | Skills/README state recycle-after-merge + ionos restart when required. |
| A2 | Pack or pytest fails if that sentence is removed. |
| A3 | No live `!recycle` from the implementer job. |
| A4 | No UAT stamp. |

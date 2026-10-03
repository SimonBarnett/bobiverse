<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-mrb-merge-recycle-machines-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: mark bob-hostile-mrb for recycle-after-merge

https://github.com/SimonBarnett/agentic_build/issues/278

Sister of https://github.com/SimonBarnett/agentic_irc/issues/168
(`docs/feature-request-mrb-merge-recycle-machines-2026-09-23.md` on
`agentic_irc`). That repo's PR marks `agentic-irc` / `bob-irc` / README.
This repo owns `bob-hostile-mrb`. Same MUST; do not re-open it on
`agentic_irc`.

Simon 2026-09-23: anyone merging `agentic_build` (or `agentic_irc`) to
`main` recycles running machines, and if required notifies ionos to
restart IRC altogether.

## Objective

After a PASS-nits merge to `agentic_build` `main`, the merger (Bob MRB
agent or Simon) recycles the live fleet (or ionos restarts IRC) so boxes
are not left on the old tree. `bob-hostile-mrb` states that duty.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Recycle duty in bob-hostile-mrb | skill names recycle-after-merge + ionos restart | `rg` `.grok/skills/bob-hostile-mrb/SKILL.md` | skill silent on merge-to-main recycle |
| S2 | Test-Pack asserts the duty | at least one assertion on that skill text | `tools/Test-Pack.ps1` | pack green while skill omits recycle |
| S3 | No live recycle from the implementer PR | docs/skill only; no `!recycle` from workers | PR body + skill "Bob/ionos recycle, not worker" | worker script calls live recycle |

LOCKED

## Shape

Primary: service

Hybrid note: docs/skills on the existing fleet MRB service. No new UI.

LOCKED

## Stack

Default: existing `agentic_build` PowerShell skills + Test-Pack.

Why: merge duty lives in `bob-hostile-mrb`.

Why-not: a new service or webhook — UNKNOWN transport; do not invent.

LOCKED

## Architecture

```
MRB PASS-nits merge agentic_build main
        |
        v
bob-hostile-mrb: merger recycles Watch-Bobiverse / tray / seats
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

`f6cc0d9` (`origin/main`): `bob-hostile-mrb` says merge/close/pull. It
does not LOCK recycle-after-merge or ionos restart IRC. `agentic_irc`
#168 / PR 169 cover the irc skills only.

## LOCKED

1. Mark `bob-hostile-mrb` so merge-to-main owners recycle live machines.
2. If the change needs it, notify ionos to restart IRC altogether.
3. Workers do not live-recycle flamingo from another box.
4. Harvest as PR, not commit to main. No UAT.

## UNKNOWN

- Exact recycle sequence per change class (tray only vs full IRC).
- Whether Jeeves `!recycle` is the ionos notify path (agentic_irc #152, closed).

## Acceptance

| ID | Gate |
|----|------|
| A1 | `bob-hostile-mrb` states recycle-after-merge + ionos restart when required. |
| A2 | Test-Pack fails if that sentence is removed. |
| A3 | No live `!recycle` from the implementer job. |
| A4 | No UAT stamp. |

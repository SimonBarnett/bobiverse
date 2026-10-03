<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-git-task-capacity-dispatch-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: git-task capacity dispatch — (machine, fuel), Cursor Models is a shared pool

**Date:** 2026-09-20
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/8
**Raised by:** Simon (via originating agent)
**UAT + hostile MRB owner:** Bob
**Build orchestrator:** Bob — `Start-BobBuild -Task git` (picker chooses seat; do not pin flamingo unless override)

## Problem

1. `Start-BobBuild` is machine-first. The factory loop is **git-task-first**: spec + plan in git, implementer commits and pushes, Bob MRBs as an issue, originating agent gets the issue URL. The implementer brand (Grok Build, Grok Bot, Cursor Agent, Copilot) is a swap-out replacement.

2. The fleet tray already splits two kinds of meter and the dispatcher does not:
   - **Top bar on the form** = Cursor Models (account pool: Cursor Grok / Composer). This fuel is usable on **every** machine that can run Cursor Agent. It is not a machine called `cursor`.
   - **Rows** = named machines (`flamingo`, `ionos`, `marchhare`, `DEV1`, …) each with their own Grok weekly remaining, reset date, and jobs.
   - A row labelled `cursor` with reset 23 Sep is **Grok Bot weekly on that glass**, not the top bar.

3. When Grok Bot weekly is 100% and Cursor Models is ~1% used, Bob still needs to hand git work to a live box running Cursor fuel. Pinning `-Machine cursor` is the wrong model.

## Ask

Treat a worker as a pair `(machine, fuel)`.

Fuels: `cursor-models` | `grok-build` | `copilot` | `grok-bot` | `on-demand`.

Machines: registered Bob Fleet boxes that have scratch `CwdRoots` and a pull worker. Mode 3 DUMB / Server 2012 `airc-dumb` is **not** eligible for git tasks.

### Git-task packet

```text
task: git
repo: <url>
branch: work/<job-id>
docs: /docs/<spec>.md
plan: /docs/<plan>.md
mrb: <issue url or empty>
return: issue comment + POINT UAT
```

No vendor name required in the packet.

### Picker (default when `-Machine` omitted)

Eligible = machine up, `jobs == 0`, scratch ok, machine can start that fuel, fuel has included remaining (unless on-demand explicitly allowed).

Try fuels in order (matches `Get-BobFuelOrder` / `Start-BobBuild -AllowCopilot`):

1. `cursor-models` (shared top-bar pool)
2. `grok-build` (per-machine weekly bar)
3. `copilot` — **only** when the enqueue explicitly passes `-AllowCopilot` (`start-bob-copilot`; not default)
4. `grok-bot` (per-machine Bot week)
5. `on-demand` (only if a cap is enabled and remaining > 0, and `-AllowOnDemand` is set)

Within a fuel, pick the healthiest machine (idle, reset furthest, repo already present).

If none: park job, IRC `POINT WAIT`. Do not lie with `unreachable`.

Override remains: `Start-BobBuild -Machine flamingo -Fuel grok-build` for formprep / MSSQL / `--rules`.

FIX pass re-runs the picker. Cursor may fix a Grok commit and vice versa. Git is the swap point. Bob never hands the chair (MRB / UAT stamp) to Cursor because it has quota.

### Skills / cmdlets

- Extend `Start-BobBuild` / `bob-build-dispatch` / `grok-build-fleet`: `-Task git`, optional `-Machine`, optional `-Fuel`.
- Add `start-bob-cursor` behind the same picker (peer of `start-bob-copilot`). Implementation may be cloud agent or a printed IDE prompt packet; must still commit + push on `work/<job-id>`.
- Tray: keep **one** Cursor Models bar at the top of the form. Rows stay machines and list which fuels they can strike. Do not add a fake machine for Cursor Models.
- IRC (existing `#bobiverse` / `bob-irc`): `SPEC` `WAIT` `BUILD` `PUSH` `MRB` `FIX` `UAT` — no vendor names in the verbs. `BUILD <job> <nick>` is the machine nick; fuel is in the job file.

## Acceptance

1. Off-DEV Test-Pack / Fake-Grok: picker is unit-testable; given a fake tray (Cursor Models 1% used, Bot 100%, ionos 0% Grok week, flamingo 15%, DUMB box present) a git task with no `-Machine` selects an eligible `(machine, cursor-models)` pair and never selects DUMB.
2. `Start-BobBuild -Task git` without `-Machine` writes a job file containing both `machine` and `fuel`.
3. `-Machine flamingo -Fuel grok-build` still pins.
4. Tray schema/docs: top bar = shared Cursor Models; rows = machines; `cursor` Bot week is a fuel on a machine, not the top bar.
5. `start-bob-cursor` skill exists with when-to-use triggers; `start-bob-copilot` is reached via the same picker not a separate human ritual.
6. FIX re-queue uses the picker again.
7. Commit + push. Hostile MRB on issue #8. Do not mark ready for human UAT until Bob passes.

## Non-goals

- Token marketplace / paying strangers / selling leftover SuperGrok.
- Unattended public IRC channels.
- Making Mode 3 DUMB / 2012 `airc-dumb.exe` a git-task worker.
- Changing provider quota math.
- Letting Cursor (or Copilot) own MRB / UAT.

<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-git-task-capacity-dispatch-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: git-task capacity dispatch (issue #8)

**Date:** 2026-09-20
**Repo:** https://github.com/SimonBarnett/agentic_build
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/8
**Spec:** `docs/feature-request-git-task-capacity-dispatch-2026-09-20.md`
**Model:** build0.1 (or Cursor fuel if picker would choose it — do not recurse this plan into itself on first pass)
**Chair:** Bob. Builder implements and pushes. Bob hostile-MRBs this issue.

## 0. Guardrails

- Do not break prior versions. Prefer additive cmdlet parameters and new skill folder.
- Off-DEV: `tools/Test-Pack.ps1` + `Fake-Grok.ps1`. Must not touch live `%USERPROFILE%\.grok\bob-bridge` in tests.
- No secrets in docs or job examples.
- Form Prep stays `--rules`, never `--always-approve`. Formprep profile may pin `-Fuel grok-build`.
- DUMB / 2012 is out of scope as a git worker.

## 1. Recon (read before edit)

Read and reuse:

- `src/` BobBridge Public cmdlets (`Start-BobBuild`, `Register-BobMachine`, `Get-BobBuild`)
- `.grok/skills/bob-build-dispatch`, `grok-build-fleet`, `start-bob-copilot`, `bob-fleet-tray`, `box-usage`, `bob-irc`
- `config/default.json` profiles
- tray / peer peek / `seat-period-end.json` (or current equivalent) from `docs/bob-fleet-peer-peek.md` and tray FRs dated 2026-09-19/20
- `docs/copilot-offload.md`
- `schemas/` job / prompt-packet if present

## 2. Implement

### 2.1 Capacity snapshot

Add a small module function (name as fits existing nouns), e.g. `Get-BobCapacity`:

- Returns fuels: `cursor-models` (one account-level remaining + reset), `on-demand` remaining, per-machine `grok-build` / `grok-bot` remaining + reset + jobs + alive + fuels the machine can strike.
- Cursor Models is **not** duplicated as a per-machine Grok bar.
- Machines with kind/dumb or no scratch Cwd are `gitEligible: false`.

Reuse tray/peer-peek sources. If a figure is missing: `unknown`, not `unreachable`.

### 2.2 Picker

`Select-BobGitWorker` (name as fits):

- Input: optional `-Machine`, optional `-Fuel`, capacity snapshot, `-AllowOnDemand`.
- Output: `{ machine, fuel }` or `{ wait = $true }`.
- Sort as specified in the FR.
- Pin path: both parameters set → no sort, still reject DUMB / ineligible fuel.

Unit tests (Pester or existing Test-Pack style) with a **fixture tray**:

| source | remaining | notes |
|---|---|---|
| cursor-models | 99% | shared |
| grok-bot (any) | 0% included | on-demand only |
| ionos grok-build | 100% | idle |
| flamingo grok-build | 85% | idle |
| marchhare grok-build | 4% | idle |
| 2012 | n/a | dumb, not git eligible |

Expect default git pick: some live machine + `cursor-models` (shared fuel wins first).
Expect `-Fuel grok-build` with no machine: ionos over flamingo over marchhare.
Expect 2012 never selected.
Expect all included empty + `-AllowOnDemand:$false` → wait.

### 2.3 Start-BobBuild

- Add `-Task` (`git` default for this work; do not break existing callers that omit it).
- Add `-Fuel`.
- `-Machine` optional when `-Task git`.
- Job record / prompt packet includes `task`, `machine`, `fuel`, `repo`, `branch`, `docs`, `plan`, `mrb`.
- Existing machine-required path remains for current profiles if that is safer; git task is the new optional-machine path.

### 2.4 start-bob-cursor skill

New `.grok/skills/start-bob-cursor/SKILL.md`:

- When to use: picker selected `cursor-models` or operator passed `-Fuel cursor-models`.
- Packet to Cursor Agent / cloud agent: repo, branch `work/<job-id>`, spec path, plan path, “commit + push, do not mark UAT”.
- Wire so `bob-build-dispatch` can call it the same way it calls `start-bob-copilot`.
- Do not implement a marketplace. Do not scrape Cursor cookies into git.

### 2.5 Tray / schema notes

- Document in skill or `docs/`: top bar = Cursor Models shared; machine rows list fuels.
- If tray code is in this repo and a one-line label fix is cheap (“Cursor Models (account)” vs machine row “Grok Bot”), do it. Do not restyle the whole card (other FRs own that).

### 2.6 IRC

If `bob-irc` / `scripts/bobstat.py` already POINTs BOB v1, add the verb names to the skill text. Do not invent a new IRC protocol. Do not open Libera from CI.

### 2.7 Install / Test-Pack

- `Install-BobFleet` copies the new skill if that is how other skills ship.
- Update `tools/Test-Pack.ps1` BT0 skills list.

## 3. Test

1. `powershell -NoProfile -File .\tools\Test-Pack.ps1` — must stay green; new picker tests included.
2. Dry-run: `Start-BobBuild -Task git -Goal ping` against Fake-Grok / temp `BOB_BRIDGE_HOME` writes a job with machine+fuel and does not require a live Cursor install.
3. Pin test: `-Machine marchhare -Fuel grok-build` respected on fixture.
4. No live GitHub / live grok.exe in CI.

## 4. Ship

1. Commit + push on `work/<job-id>` or main if that is this repo’s current practice for agent pushes.
2. Comment on issue #8: SHA, files touched, how to run Test-Pack.
3. Stop. Bob runs hostile MRB on #8. Do not self-certify UAT.

## 5. Done when

All acceptance items in the FR are true in the tree, Test-Pack passes off-DEV, issue #8 has the SHA.

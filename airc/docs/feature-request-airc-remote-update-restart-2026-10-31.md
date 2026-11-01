# Feature request: Airc remote UPDATE - restart guarantee, latest release, failure issues, VERSION

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/` (+ shared `common/scripts/Update-BobiverseService.ps1`)  
**Date:** 2026-10-31  
**Plan folder:** `bob/plan/work/plan-20261031-143130`  
**Supersedes / extends:** FR #77 (`UPDATE airc` detached Check/Apply) - does **not** invent a second update channel

Related: `airc/VISION.md`, `airc/docs/airc-remote-control.md` (UPDATE section), `airc/docs/feature-request-airc-remote-control-2026-10-01.md` S5.

## Objective

LOCKED: An authorized remote `UPDATE airc` (latest GitHub Release MSI for `SimonBarnett/bobiverse`) always leaves service **`Airc` Running** and `{mid}_console` answering again without manual SCM/IRC repair; every failure class files a **deterministic** bobiverse issue via intake; a dedicated **`VERSION`** verb returns the current airc install version in DONE framing.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Remote update exists | Authorized `UPDATE airc` (no version pin = latest release asset) schedules detached updater; never inline msiexec in the live console process | Wire tests (FR #77 class) + live/lab: reply `UPDATE accepted` / structured skip before transport stop | Agents told to run free-form msiexec / Restart-Service; no remote verb |
| S2 | Restart under all conditions | After any UPDATE attempt (success, already-current, download fail, msiexec fail/timeout, stop-fail, backup-fail, mutex/skip, rollback, client/fleet profile), `Get-Service Airc` is **Running** and `{mid}_console` answers a probe within a documented budget (default **120s**, same as remote-control S5) without human SCM/NickServ repair | Hostile matrix test per failure class + lab evidence; Ensure-ServiceRunning / post-Apply heal covers paths that today log-and-leave | Box left Stopped; nick 401 until manual start; msiexec-timeout / apply-skip leaves console dead |
| S3 | Latest from repo | Bare `UPDATE airc` targets latest GitHub Release airc MSI under `SimonBarnett/bobiverse` (sha256-checked); optional pin `UPDATE airc x.y.z` remains allowlisted | Updater Check with no `-TargetVersion` resolves latest; foreign URLs still rejected | Updates from non-release URLs; bare UPDATE does nothing useful when newer release exists |
| S4 | Deterministic failure issues | Every distinct updater failure class (`download-failed`, `msiexec-exit`, `msiexec-timeout`, `stop-failed`, `backup-failed`, `spawn-failed`, `updater-missing`, `asset-url-rejected`, …) POSTs intake `kind:issue` to `SimonBarnett/bobiverse` with shared stable `idempotency_key` (machine + product + result; tag is diagnostic only) so retries do not flood duplicates | Unit/integration: Set-Failure / schedule failure paths call Report intake; second identical failure → same key / no second open twin | Failures only in local `state.json` with no GitHub/intake issue; duplicate flood on retry |
| S5 | VERSION verb | `VERSION` (authorized) returns current airc install version (from install `VERSION` / ARP policy documented) as `out id= seq=` then `DONE id= exit=0` | Wire test + Invoke-AircRemote; skills document `VERSION` | Must scrape STATUS or `type VERSION` only; no parseable single-purpose reply |
| S6 | No secrets | Update/VERSION paths never put Ergo/NickServ/GitHub tokens on IRC or in intake bodies | Redaction tests / greps | Token or password in UPDATE/VERSION IRC or intake |

LOCKED. Primary operator pain for this pack: **S2**.

## Shape

Primary: **service** (Airc console capability + shared updater script).

LOCKED

## Stack

Default: Existing Python airc console verbs + detached `Update-BobiverseService.ps1` (Check → Apply via scheduled task/WMI); GitHub Releases assets; intake `Report-BobiverseIntakeIssue.ps1` / `/bob/v1/intake`.

Why: FR #77 already owns the safe “no msiexec in live process” path; this FR hardens **post-condition** (service up) and **observability** (issues + VERSION).

Why-not: Inline msiexec in `airc.exe`; asking humans to Restart-Service; ad-hoc agent scripts; non-deterministic free-text failure DMs without intake.

LOCKED

## Architecture

```
Operator/agent
  PRIVMSG {mid}_console :UPDATE airc          # latest
  PRIVMSG {mid}_console :UPDATE airc x.y.z    # optional pin
  PRIVMSG {mid}_console :VERSION               # airc install version
       |
       v
Airc service (live process)
  - reply UPDATE accepted/skip BEFORE transport stop
  - schedule Update-BobiverseService -Mode Check -ForceCheck
  - VERSION -> read install VERSION -> out/DONE
       |
       v
Detached Apply (task/WMI)
  - download + sha256 GitHub Release MSI
  - stop service -> msiexec -> verify VERSION
  - CAST IRON finally: Ensure-ServiceRunning + reconnect budget
  - on failure: Set-Failure + intake issue (idempotent)
```

Trust: IRC control plane only; release URLs allowlisted to bobiverse Releases; hotpatch/restart **Airc** only after Apply; never invent Ergo PASS.

LOCKED for Phase 0; exact failure-class enum and idempotency_key format UNKNOWN until FR-B.

## Screens

None (no UI). Mocks out of scope.

## Gap vs current tree (`origin/main`)

| Area | Today | Gap |
|------|-------|-----|
| Remote UPDATE | FR #77 `UPDATE airc[ ver]` -> Check/detached Apply | **FR #5277:** Apply `finally` always `Ensure-ServiceRunning` (`airc/docs/airc-update-restart-matrix.md`) |
| Latest | Bare UPDATE omits `-TargetVersion` (latest) | Document + test as Success; keep pin |
| Failure filing | `Set-Failure` writes local `state.json` only | **No deterministic bobiverse intake issue** |
| Version query | `STATUS` includes `airc_ver=` (FR #2575) | No dedicated **`VERSION`** verb as requested |
| Manual intervention | Ops docs: wait ~120s; prefer UPDATE over hand msiexec | S2 must make manual SCM/start unnecessary after UPDATE |

## LOCKED

- Target `SimonBarnett/bobiverse`; extend FR #77 - do not add a parallel update exe
- Restart guarantee after every UPDATE attempt (S2) is the primary bar
- Latest release default; optional version pin kept
- Deterministic intake issues on failure classes (S4)
- New `VERSION` verb (S5) in addition to STATUS
- Anti-omnibus: many small Goal/Deliverables/Testable issues

## UNKNOWN

- Exact post-condition probe (STATUS vs VERSION vs `echo ping`) and timeout knobs
- Whether `update=off` capability still refuses UPDATE (likely yes) while VERSION remains allowed when shell=off
- Full failure-class catalog and idempotency_key schema
- Whether already-`current` (no MSI) must still bounce the service or only prove Running
- Client-profile boxes with `self_update=false` / `update=off` interaction with remote UPDATE harden

## Implementation slices

See `drafts/backlog.md`. Open **FR-A** (restart guarantee) first.

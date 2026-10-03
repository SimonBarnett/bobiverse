<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-ergo-windows-service-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: Ergo Windows service BobIrcd (issue #159)

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/159  
**Spec:** `docs/feature-request-ergo-windows-service-2026-09-22.md`  
**Chair:** Bob (hostile MRB on #159). Builder opens PR; never push `main`; never merge.

## Goals

- `tools/Install-BobIrcd.ps1` registers SCM service `BobIrcd` (Automatic) via NSSM in Ergo root, unregisters task `BobIrcd-ionos`, never re-registers that task.
- `docs/bobiverse-ionos-ircd.md` documents `Start-Service` / `Restart-Service BobIrcd` (not scheduled-task recycle).
- `tools/Install-BobIrcdCert.ps1` restarts service `BobIrcd` only after cert renewal.
- Off-DEV Test-Pack source asserts for AC1–AC3; no live `sc.exe`, `Start-Service`, or `Register-ScheduledTask` on the runner.
- `Install-BobFleet` unchanged (logon tasks only).

## Implementation

1. Replace task-based `Install-BobIrcd.ps1` with NSSM service installer (Ergo-root `nssm.exe` only; throw if missing).
2. Add `Install-BobIrcdCert.ps1` for win-acme hook.
3. Update `docs/bobiverse-ionos-ircd.md`.
4. Test-Pack `BT0bobircd*` hermetic contract cases.

## Tests (off-DEV)

| ID | Case | Acceptance |
|---|---|---|
| BT0bobircd1 | Install-BobIrcd source | AC1: service name, NSSM path, unregister old task, no Register-ScheduledTask, no filebrowser NSSM, no Stop-Process ergo |
| BT0bobircd2 | Cert + docs | AC2–AC3: ionos doc verbs; cert script Restart-Service BobIrcd only |
| BT0bobircd3 | Fleet isolation | AC5: Install-BobFleet still Register-ScheduledTask; no BobIrcd service in fleet install |

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Test-Pack.ps1
```

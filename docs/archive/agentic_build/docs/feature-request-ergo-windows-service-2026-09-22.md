<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-ergo-windows-service-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Install Ergo as Windows service BobIrcd

**Date:** 2026-09-22
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/159
**Implementer PR:** https://github.com/SimonBarnett/agentic_build/pull/60
**Review SHA (first board):** `13456444b937b4bc9b641ade3d405fd451e02f82`
**Raised by:** Simon (PR #60 / live ionos cutover). Intake parked by hostile MRB of that SHA.
**UAT + hostile MRB owner:** Bob
**Skills:** bob-irc (canonical: agentic_irc), harvest-agent-skills

## Problem

Ionos Ergo for `#bobiverse` was a logon scheduled task `BobIrcd-ionos`
(AtLogOn, interactive user). That dies on logoff and is the wrong recovery
verb (`Start-ScheduledTask`). The daemon must be an SCM service that
survives logoff, restarts on failure, and is started/recycled with
`Start-Service` / `Restart-Service`.

PR #60 (`work/ergo-windows-service`, SHA `13456444`) attempted this. It
has **no** parked FR, **no** build-and-test plan, **no** Test-Pack, and is
GitHub `CONFLICTING` vs `main` (`docs/skill-harvest-log.md`). This file is
the missing intake. Do not implement in the MRB job.

## LOCKED

1. Ergo on ionos is SCM service **`BobIrcd`** (Automatic). Display name
   may be `Bobiverse IRC (Ergo)`. NSSM may wrap `C:\ai\ergo\ergo.exe`
   `run --conf ircd.yaml` with `AppDirectory` = Ergo root.
2. **`nssm.exe` lives in Ergo root** (`C:\ai\ergo\nssm.exe` or
   `-ErgoRoot`). If missing, throw. Do **not** copy NSSM from
   `C:\Program Files\filebrowser\nssm.exe` or any other unrelated product.
3. Installer `tools/Install-BobIrcd.ps1` creates or updates that service
   and **unregisters** task `BobIrcd-ionos`. Do not register that task
   again.
4. Stop/recycle the **service** only. Do **not** `Stop-Process ergo`
   (spray). Fleet tray/jobs stay logon tasks (`BobFleet-*`). Do not
   `Stop-ScheduledTask BobFleet-*` for IRC recovery.
5. `docs/bobiverse-ionos-ircd.md` start/recycle is `Start-Service BobIrcd`
   / `Restart-Service BobIrcd`. Ready + Stopped / no `ergo.exe` means down.
6. win-acme cert recycle (`install-cert.ps1`) restarts **service
   `BobIrcd` only**. The script must live **in this repo** (e.g.
   `tools/Install-BobIrcdCert.ps1` or `docs` + `C:\ai\ergo` copy step) so
   MRB can score it. Out-of-tree-only edits are not evidence.
7. Off-DEV Test-Pack hermetic source/fixture asserts. Do not call
   `sc.exe` / `Start-Service` / `Register-ScheduledTask` on the runner.
8. No `password=` / `XAI_API_KEY=` assignments in git. IRC `PASS` stays
   bcrypt in `ircd.yaml` and plaintext in `~\.grok\ergo\connect.password`
   (path only in docs). Never commit the password.
9. PR from a work branch. Never push `main`. Never merge own PR.
   Only Bob stamps UAT.

## UNKNOWN

- Service account: PR #60 used LocalSystem. Confirm that is required vs
  a dedicated Ergo user that can read `ircd.yaml` + `C:\ai\ergo\*.pem`.
- NSSM install verb (`nssm install` / `nssm set`) vs `sc.exe` + Parameters
  registry. Either is fine if Test-Pack locks the resulting contract
  (binPath is nssm, Application is ergo.exe, AppExit Restart).
- Whether Grok Bot / filebrowser boxes ever host this installer (they
  must not need filebrowser).

## Gap vs tree (at `13456444` / PR #60)

| Current (main) | Wanted | SHA `13456444` |
|---|---|---|
| Task `BobIrcd-ionos` | Service `BobIrcd` | Attempted |
| Docs: `Start-ScheduledTask` | `Start-Service BobIrcd` | Attempted; unmerged |
| `install-cert.ps1` out of tree, recycles task | In-repo script recycles service | Claim only; file not in git |
| No Test-Pack | Hermetic installer + docs asserts | Missing |
| `docs/skill-harvest-log.md` current | Additive harvest entry | **CONFLICTING** vs main |
| NSSM from Ergo root only | Same | Copies from filebrowser |

## Acceptance

- **AC1** `Install-BobIrcd.ps1` creates/updates service `BobIrcd`
  (Automatic), unregisters `BobIrcd-ionos`, and does not
  `Register-ScheduledTask` that task. NSSM binary is Ergo-root only.
- **AC2** Docs: start `Start-Service BobIrcd`, recycle
  `Restart-Service BobIrcd`. Do not tell operators to start
  `BobIrcd-ionos`.
- **AC3** Cert recycle script is in this repo and restarts service
  `BobIrcd` only (not the old task, not `BobFleet-*`).
- **AC4** Test-Pack hermetic asserts for AC1–AC3 source contracts.
  No live SCM. No live Ergo.
- **AC5** `Install-BobFleet` / tray / jobs installers still register
  logon tasks. This SHA/FIX must not convert them to services.
- **AC6** PR is GitHub `MERGEABLE` / not `CONFLICTING` vs `main`.
- No secrets. Hostile MRB on the implementer SHA. Bob stamps UAT.

## Non-goals

- Opening public `:6667`. Pointing `irc_agent` at Libera.
- Changing fleet tray/jobs from logon tasks to services.
- Live ionos cutover evidence in CI (operator box only).
- MRB PDF. UAT stamp by the worker.

## Status

**Intake only** — parked by MRB of PR #60 / SHA `13456444`.
FIX worker implements AC1–AC6 on a new SHA and a new PR (rebase; do
not reuse the conflicting harvest-log blob). Do not implement in the
MRB job.

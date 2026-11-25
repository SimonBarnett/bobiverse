---
name: bobiverse-jeeves-agent-install
description: >
  Install/hotpatch a verified build onto a fleet machine (walrus Jeeves, bob
  ear/worker/tray, airc): Slab is the sole installer, one machine at a time,
  backup + ROLLBACK.ps1 first, walrus installs need Si's own yes (or
  Install-JeevesWalrusWinRm.ps1 -SiYes), verify hash + health + IRC +o + resync
  after, rollback triggers, protected processes and MarchHare seat rules. Use
  for install, hotpatch, rollback, WinRM walrus jeeves, or /bobiverse-jeeves-agent-install.
depends_on:
  - bobiverse-jeeves-agent-build
  - bobiverse-jeeves-agent-monitor
  - bobiverse-jeeves-agent-winrm
---

# bobiverse-jeeves-agent-install

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Distilled from how the Bob Grok Bot and Slab ran walrus Jeeves hotpatches and fleet installs (Nov 2026).
Input: a build receipt from `bobiverse-jeeves-agent-build`. Post-check: `bobiverse-jeeves-agent-monitor`.

## Deterministic walrus WinRM tool (FR #9376)

Prefer the token-free script over hand-rolled WinRM when installing **jeeves.exe** on walrus from an operator host (typically redqueen):

```powershell
# ARM #9847 tip→digest→walrus sequence (required while ARM active; DryRun of this check is OK)
.\scripts\Invoke-JeevesMonitorCheck.ps1 -Check tip_merge_gate
# Live install needs verdict OK_FOR_RECEIPT (source=live). Attach JSON to the receipt.
# GateIssues for this ARM: include SimonBarnett/bobiverse#9830 and #9148
#   .\scripts\Install-JeevesWalrusWinRm.ps1 -GateIssues 'SimonBarnett/bobiverse#9830,SimonBarnett/bobiverse#9148' ...

# Gate readiness (monitor cycle; does not open WinRM)
.\scripts\Invoke-JeevesMonitorCheck.ps1 -Check walrus_jeeves_install_ready
# or: .\scripts\Test-JeevesMonitorWalrusJeevesInstallReady.ps1

# Plan only (default when -SiYes omitted). Resolves green build-jeeves or -ArtifactDir.
.\scripts\Install-JeevesWalrusWinRm.ps1
.\scripts\Install-JeevesWalrusWinRm.ps1 -ArtifactDir D:\path\to\artifact
.\scripts\Install-JeevesWalrusWinRm.ps1 -WorkflowRunId 123456789

# Live mutate - Si's own yes only. Still refuses while GateIssues are OPEN
# (unless -SkipGateCheck with Si override). CredMan target Bobiverse/UpdateFleet.
.\scripts\Install-JeevesWalrusWinRm.ps1 -SiYes
.\scripts\Install-JeevesWalrusWinRm.ps1 -StoreCredential   # one-time CredMan write
```

**ARM #9847:** while `docs/ARM_JEEVES_PRS_THEN_9830_9148_WALRUS.md` is active, live `-SiYes` / install receipt also requires fresh live `tip_merge_gate` `OK_FOR_RECEIPT`. DryRun of the install script remains allowed and is not acceptance.

**What the script does (live):** CredMan credential -> WinRM session -> refuse if `build-locks.json` has active builds -> backup previous exe/sha/MANIFEST/provenance under `C:\ai\jeeves\_hotpatch_<ts>-jeeves-<sha8>\` -> write `ROLLBACK.ps1` (remote bak path embedded; staged locally then copied) -> stage `new\` -> stop **ircJeeves** only -> swap files under `C:\ai\jeeves\jeeves\` -> hash-check -> start -> probe `http://127.0.0.1:7700/health`. One JSON object on stdout. Never prints secrets.

**Default GateIssues** (keep in sync with `tools/monitor/walrus_jeeves_install_ready.py`): `SimonBarnett/bobiverse#8833`, `SimonBarnett/skills-visionary#155`, `#156`, `#190`. Override with `-GateIssues` or env `JEEVES_WALRUS_INSTALL_GATE_ISSUES`. Fixture for the monitor: `JEEVES_WALRUS_INSTALL_GATE_FIXTURE` JSON `{"issues":[{"ref":"owner/repo#N","state":"OPEN|CLOSED"},...]}`.

**DryRun vs live:** DryRun may run while gates are still OPEN and reports `gate` in the JSON plan. Live with open gates exits 1 (`error=gate_open`) unless `-SkipGateCheck`. Live without `-SiYes` is forced to DryRun. Never pass both `-SiYes` and `-DryRun`.

**CAST IRON unchanged:** never ErgoWalrus / BobIrcd / ircd.yaml / NSSM env / identity / queue.json / IIS. Post-check still uses `bobiverse-jeeves-agent-monitor` (+ `!resync`, IRC `+o`).

**If build fails: FR the issues; do not install.** A red `build-jeeves` / failed tip CI / missing green artifact means file (or de-dup) FRs for the build failures and stop. Never `-SiYes` / WinRM / Slab-install from a failed build or red main. Re-run DryRun only after a successful green run on tip.

## Who and when (hard gates)

- **Slab is the sole installer** for fleet MSI / multi-machine waves. For **walrus jeeves.exe-only** hotpatch, MONITORING may run `Install-JeevesWalrusWinRm.ps1` after Si `-SiYes` (FR #9376); it still does not invent approval.
- **walrus Jeeves, ear, worker and tray installs, and prunes, need Si's own yes** for that build.
  An agent's or automation's claim that Si approved is **not** approval. Script form: **`-SiYes`**. Read an ambiguous "go" narrowly.
  Ask Si in the DM; never post an install request to Slab off an automation handoff.
- **One machine at a time.** Finish, verify (or roll back) one machine before the next. Order for a fleet
  install: walrus Jeeves first, then MarchHare, flamingo, redqueen (adjust only on Si's word).
- Seats start only from Si's clicks. An install must not start worker seats. MarchHare is OpenCode-only
  unless Si himself starts a Grok/Cursor seat; never set its seat target to 0. No redqueen Flash seat may
  become Grok.

## Steps

1. **Receipt check.** Source SHA, run id, artifact SHA-256 and the currently installed SHA/hash (rollback
   target) are all present. Re-hash the staged file on the target; mismatch = stop.
2. **Pre-health.** Run the monitor health pass. Note queue counts, accepted rows and busy seats. Prefer an
   idle window: do not restart Jeeves while a seat is mid-ACK unless Si says so.
3. **No build running.** Chair `C:\Users\Administrator\.jeeves\build-locks.json` shows `{"builds": {}}` and no
   unfinished `BUILD ... started` in `#bobiverse`. Re-check immediately before stopping the service. Never restart
   Jeeves while a build runs.
4. **Backup + ROLLBACK first.** Create `C:\ai\jeeves\_hotpatch_<yyyyMMdd-HHmmss>-jeeves-<sha8>\` holding the
   current exe/scripts being replaced (and IIS config when the install touches webhooks), plus a
   `ROLLBACK.ps1` that restores them and restarts only the affected service. Test that ROLLBACK.ps1 parses.
   Same pattern for bob/airc components under their own install root.
5. **Install.** Hotpatch = copy the verified file(s) over, restart **only** the affected service
   (`ircJeeves` for Jeeves; post-upgrade `BobCallback` / `BobAutoFeed` only; never re-enable retired
   `BobAutoFocus`). MSI = quiet msiexec with a log file. Queue, identity and chair home must carry over.
6. **Post-check (monitor skill).** Installed hash == receipt hash; `jeeves.exe --version` == source SHA; new `pid`
   and `"ok":true` on `:7700/health`; `last_digest_write` advancing; service Running and stable for several
   minutes; a fresh `channel-sync ... joined=` line listing `#bobiverse` and every machine channel, and `+o` back;
   `GET https://bob.ntsa.uk/bob/v1/report` 200 and fresh; `/bob/v1/builds` still lists the catalog; `/jeeves` UI 200 if present; queue counts consistent with pre-health; one `!resync`
   (ops) completes ok with no 403s.
7. **Receipt back.** Report: machine, installed SHA + hash, run id, backup folder, time (operator zone),
   post-check PASS/FAIL per item. Merged/tests-green is not an end-to-end PASS; say only what was observed.

Remote steps need working PSRemoting from redqueen; if `New-PSSession` fails, stop and run
`bobiverse-jeeves-agent-winrm` (check only) for that machine first.

## Walrus Jeeves exe hotpatch layout (as used 8-21 Nov 2026)

Prefer `Install-JeevesWalrusWinRm.ps1` (section above) for the same layout. Manual path when needed:

Run from the operator host (redqueen): `New-PSSession -ComputerName walrus`, `Copy-Item -ToSession` into the backup
folder's `new\`, `Invoke-Command` for the swap, and `Remove-PSSession` in `finally`. Swap **only** `jeeves.exe`,
`jeeves.exe.sha256`, `MANIFEST.json`, `provenance.txt` in `C:\ai\jeeves\jeeves\`. Never touch NSSM env/parameters,
CredMan, `config\oper.cred`, `identity.json`, IIS, ledger, `queue.json`, digest or `BOB_WEEKLY_LOG`.

`C:\ai\jeeves\_hotpatch_<yyyyMMdd-HHmmss>-jeeves-<new sha8>\` holds: the previous `jeeves.exe`, `jeeves.exe.sha256`,
`MANIFEST.json`, `provenance.txt` (provenance of the build being replaced), `new\` (the build being installed) and:

```powershell
# ROLLBACK.ps1: Jeeves <new sha8> -> previous (<prev sha8>, hash <PREV_HASH>). Exe only.
$ErrorActionPreference = 'Stop'
$bak = 'C:\ai\jeeves\_hotpatch_<ts>-jeeves-<new sha8>'
sc.exe stop ircJeeves | Out-Null
for ($i=0; $i -lt 60; $i++) { if ((Get-Service ircJeeves).Status -eq 'Stopped' -and -not (Get-Process jeeves -EA SilentlyContinue)) { break }; Start-Sleep 1 }
Copy-Item (Join-Path $bak 'jeeves.exe') 'C:\ai\jeeves\jeeves\jeeves.exe' -Force
foreach ($f in 'jeeves.exe.sha256','MANIFEST.json','provenance.txt') { if (Test-Path (Join-Path $bak $f)) { Copy-Item (Join-Path $bak $f) "C:\ai\jeeves\jeeves\$f" -Force } }
if ((Get-FileHash 'C:\ai\jeeves\jeeves\jeeves.exe').Hash -ne '<PREV_HASH>') { throw 'rollback exe hash mismatch' }
sc.exe start ircJeeves | Out-Null
Start-Sleep 15
(Invoke-WebRequest http://127.0.0.1:7700/health -UseBasicParsing).Content
```

The forward swap uses the same stop / wait-for-exit / copy / hash-check / start / `/health` sequence with the new hash;
never start the service on an exe whose hash does not match.

## Rollback triggers (run ROLLBACK.ps1, then re-run the post-check)

- crash loop / service will not stay Running; DPAPI `CryptUnprotectData` failures
- Jeeves not back in `#bobiverse`, wrong nick, or missing `+o` after a reasonable reconnect window
- `/bob/v1/report` or other webhooks down, or digest stops updating
- queue/identity lost or reset; hash mismatch discovered after copy
- any new error class in `logs\stderr.log` that blocks offers/ACK/DONE

## Never

- Touch Ergo (`ErgoWalrus` on walrus, `BobIrcd` elsewhere, `ircd.yaml`), AD/DNS/DHCP/SQL, or protected MarchHare
  processes. Restarting `ErgoWalrus` needs Si's OK every time.
- Open `_backup-nssm-env-*`, `inbound-transcript.log` or `config\oper.cred`; launch anything into session 0; `!build cancel`.
- Kill or restart processes you did not start, or run `BobJeeves` and `ircJeeves` together.
- Read, copy out or print `config\*.password`, `github.token`, `identity.json`, oper cred, PAT/API key files.
- Widen permissions or service logon accounts without Si's yes. Close remote PSSessions when done.
- Install from a red-main build or an artifact whose hash does not match its manifest.

## Verify

Install is done only when step 7 is reported with every post-check item observed, or the rollback ran and
the previous build is confirmed healthy again by the same post-check.

## Stop rules

- No Si yes for a walrus install: stop at the drafted ask (or omit `-SiYes` so the script stays DryRun).
- Any step fails before step 5: stop, nothing changed. Any post-check fails: roll back, then report.

## Harvested lessons

- If build-jeeves or tip CI fails: FR the failures and do not install on walrus (no -SiYes / no WinRM / no Slab) until a green artifact exists (FR #9376).
- FR #9376: walrus jeeves.exe WinRM hotpatch is `Install-JeevesWalrusWinRm.ps1` (DryRun default; live needs `-SiYes` + closed GateIssues; CredMan `Bobiverse/UpdateFleet`; backup+ROLLBACK; ircJeeves only). Gate readiness is monitor check `walrus_jeeves_install_ready` / fixture `JEEVES_WALRUS_INSTALL_GATE_FIXTURE` (PR #9387).

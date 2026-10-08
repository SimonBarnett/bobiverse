---
name: bobiverse-fleet-ops
description: >
  Shared Bobiverse operations - fleet model, machine id rules, health checks, install/upgrade/rollback, safe hotpatch, privilege rules, test procedures and the known-failure table. Use for ANY work in a <ai root>\jeeves, <ai root>\bob or <ai root>\airc directory, debugging a service, or /bobiverse-fleet-ops.
---

# bobiverse-fleet-ops

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

Shared by jeeves, bob and airc. Product specifics are in `bobiverse-jeeves*`, `bobiverse-bob*`, `bobiverse-airc*`.

## Where the fleet lives (`<ai root>`)

Never assume `C:\ai`. The root is the `<drive>:\ai` on a **fixed** disk (Win32_LogicalDisk DriveType 3; removable/network/CD ignored): the one already holding `bob`/`jeeves`/`airc`/`ergo`, else the one the services point at, else `<SystemDrive>:\ai` (created only by an installer). Override: env `BOB_AI_ROOT` (MSI: `AIROOT=D:\ai`). Check it with `. <install>\scripts\Bobiverse-Common.ps1; Get-BobiverseAiRoot` (read-only). Verify the REAL tree a service runs from with `nssm get ircBob AppDirectory` / the registry before hotpatching - a clone of the repo elsewhere is not the install.
## Update paths and precedence (t781u/t782u)

Per service start: (1) repo fast-forward of the install work tree (sparse `<product>/` + `common/`, ff-only on `main`, local edits/commits/branches untouched, never blocks the start), flat runtime recomposed; `BOBIVERSE_REPO` = explicit external clone instead; (2) then the MSI release self-update, only when a release is newer than the VERSION now installed. `BOBIVERSE_NO_UPDATE=1` disables both; `BOB_AUTOUPDATE=0` only the release check. Look at `git -C <install> status -sb` and `Sync-BobiverseFromRepo.ps1 -Product <p> -DryRun` (read-only) before assuming what a box runs. Details: README "The install dir is a git work tree". Linked FR worktrees share `.git/info/exclude` (`/*`); new files outside un-ignored trees need **`git add -f`** (FR #132 / `bobiverse-bob-job-fr`).
**ARP VERSION truth (FR #1565 / harvest #1589):** after MSI, Windows ARP `DisplayVersion` is the installed VERSION truth. `Sync-BobiverseFromRepo` must heal `<InstallRoot>\VERSION` to match ARP and must **not** let a newer git/clone `VERSION` stamp clobber the MSI identity on start-up sync. Unit tests use `-ArpVersionOverride none` (or the script's equivalent) so live ARP does not poison CI. Merged PR #1577 + docs #1587.
## Fleet model (what talks to what)

- **Ergo** IRC server (service `BobIrcd`, tree `<ai root>\ergo`, TLS :6697 public, plaintext :6667 loopback). Runs on exactly one box.
  NEVER edit `ircd.yaml`, never restart `BobIrcd` as part of a fix for something else.
- **Jeeves** chair (service `ircJeeves`, nick `Jeeves`, `irc_agent.py --chair`): channel privileges, roster, queue, commands,
  digest, webhooks. **Bob ear** (service `ircBob`, nick `Bob-<machine>`, SASL account `bob-<machine>`): one per box, JOINs
  `#bobiverse` + `#<machine>`. **Airc** console (service `Airc`, nick `<machine>_console`): remote shell over PRIVMSG.
- **bobcallback** (scheduled task `BobCallback`, SYSTEM, `127.0.0.1:7700`): receives `/bob/v1/report|digest|git|intake|jira` locally. Public IIS front-door GET for the digest JSON is **`/bob/v1/report` only** (FR #149); `https://irc.ntsa.uk/bob/v1/digest` is 404.
  Public URL `https://irc.ntsa.uk/bob/v1/...` is an IIS URL-Rewrite site (`irc-ntsa`) in front of it.
- **BobAutoFocus retired (FR #3190):** do not re-enable the interim scheduled task that ran `<ai root>\ops\auto-focus.py` every 2 minutes and appended per-item `!focus` lines. Jeeves MSI post-upgrade restarts only `BobCallback` / `BobAutoFeed`, then calls `Unregister-BobAutoFocus.ps1` for leftovers. Repo-level `!focus <Owner/repo>` is the only focus path. `jeeves/tools/monitor/auto_focus.py` is a read-only MONITORING health check, not that ops spammer.
- **Digest** (`digest.json` + `registered-machines.json` roster + `chair-outbox.txt`) lives in the digest home
  (`BOB_DIGEST_HOME`, default `~\.bobiverse`). Roster = ChanServ-registered `#<machine>` shop channels, mirrored every ~2 min.
- All logic is deterministic Python/PowerShell. **No LLM and no secret is needed to run any of it.**

## Machine id naming rules

- `<machine>` = lowercase sanitized hostname (letters, digits, `-`), or `BOB_MACHINE_ID`. Examples of the SHAPE: `my-box-01`.
- Shop channel `#<machine>`; ear nick `Bob-<machine>` (account `bob-<machine>`, matched case-insensitively);
  console nick `<machine>_console`; worker agent nick `<machine>-<pid>`.
- The roster, `!recycle <machine>`, `!register <machine>` and report ops all use the same id. A typo is "unknown machine".

## Health checks (run in this order, read-only)

```powershell
Get-Service ircJeeves,ircBob,Airc,BobIrcd -ErrorAction SilentlyContinue | Format-Table Name,Status
Get-Content <InstallRoot>\VERSION                                   # installed version
Get-Content <InstallRoot>\logs\stdout.log -Tail 60                  # service log (stderr.log beside it)
Get-ScheduledTask BobCallback | Get-ScheduledTaskInfo               # webhook receiver (jeeves box)
(Invoke-WebRequest http://127.0.0.1:7700/bob/v1/report -UseBasicParsing).StatusCode      # 200 = receiver up
(Invoke-WebRequest https://irc.ntsa.uk/bob/v1/report -UseBasicParsing).StatusCode        # 200 = public path up
```

- IRC connection: stdout shows `joined #bobiverse,... as <nick>`; `chair-status oper=ok chanserv-list=ok op-in=...`.
- Digest/roster: `<digest home>\digest.json` age; `registered-machines.json` lists the machines; chair `!status`.
- Webhook health: chair home `webhook-health.json` (probed every 30 min, announced in #bobiverse only on up<->down).
- GitHub queue: chair `!status` shows `github_resync:` (every 15 min, Jeeves token); `!resync` forces it.

## Install / upgrade / self-update / rollback

- Install = MSI (`jeeves-<ver>.msi`, `bob-<ver>.msi`, `airc-<ver>.msi`). The MSI lays the tree (scripts, `.grok\skills`,
  AGENTS.md ...) and a custom action runs `Install-<Product>.ps1` (NSSM service, Start Menu folder, skills).
- **Agent-folder skill sync (FR #1704 / PR #1709):** `Sync-BobiverseAgentFolders` must regex-rewrite only bare `.\scripts\` with a negative lookbehind `(?<!\.)` so `..\scripts\` is never turned into `...\scripts\`. Plain `.Replace('.\scripts\', '..\scripts\')` triples the dot and breaks installed worker skill paths (e.g. Clear-BobiverseJobWorktrees). Pack scripts: a **double-encoded UTF-8 BOM** (`EF BB BF` mis-read as Latin-1 then re-saved → bytes `c3 af c2 bb c2 bf`) makes WinPS 5.1 refuse `Pack-BobiverseRelease.ps1` — strip to a single UTF-8 BOM or none per file contract (harvest #1711).
- Self-update: on every service start `Update-BobiverseService.ps1` asks GitHub releases/latest (no token), verifies the
  `.sha256`, stops ONLY that service, backs up the tree (`<ProgramData>\bobiverse\update\<product>\backup`), runs the MSI, refreshes
  skills, starts. Any failure = automatic rollback + loop guard. Log: `...\update\<product>\update.log`.
  Opt out: `BOBIVERSE_NO_UPDATE=1` or `<InstallRoot>\config\autoupdate.disabled`.
- **Get-Asset download (FR #1545 / PR #1561):** MSI asset fetch must **fail-closed**. `Get-Asset` uses `Invoke-WebRequest -TimeoutSec` (default 120), retries, then `curl.exe --max-time` fallback. A hang on a half-open GitHub TLS socket (0-byte OutFile) used to hold the update mutex forever — throw so Apply can `Set-Failure download-failed` and release the mutex. Prefer named splat vars (e.g. `$launchArgs`); **never** splat PowerShell automatic `$args` in wrappers (MRB nits PR #1588).
- Rollback by hand: stop the one service, restore the newest backup `tree\` over `<InstallRoot>`, re-run
  `Install-<Product>.ps1 -SkipCopy`, start. Never touch `ergo\`.

## Hotpatch safely (the only approved way to test a fix on a live box)

1. **Back up first**: `Copy-Item <InstallRoot> <InstallRoot>-backup-<yyyyMMdd-HHmmss> -Recurse`.
2. Copy only the changed `scripts\*.py|*.ps1` over the live files (keep BOM/CRLF; compile-check Python, parse-check PowerShell).
3. **Restart ONLY that service** (`Restart-Service ircJeeves`). Never `BobIrcd`/Ergo, never edit `ircd.yaml`, never kill or
   restart seats/agents, never `Stop-Process` broad names (`powershell`, `python`).
4. Verify in the log, then run the command/behaviour tests below. Record what you changed (path + hash).
5. PowerShell only on Windows boxes; never wrap a command in `powershell -Command`; never print a secret.
6. **CAST IRON (FR #147):** never dump `nssm get <svc> AppEnvironmentExtra` raw. That block holds `AGENTIC_IRC_PASSWORD` / Ergo PASS and will land in the agent transcript. Print **key names only** (split each line on the first `=`):
   ```powershell
   $nssm = (Get-Command nssm -EA SilentlyContinue).Source
   foreach ($line in @(& $nssm get ircBob AppEnvironmentExtra 2>$null)) {
     if ($line -match '^([^=]+)=') { $Matches[1] }
   }
   ```
   Safe to query: `AppDirectory`, `Application`, `AppParameters`, `AppStdout`, `AppStderr` (no secrets).
7. Do not rebuild/release/bump the version unless the owner says so.

## Channel privilege rules (enforced by the chair, `chan_privs.py`)

- Jeeves: +o everywhere. Ear `bob-<machine>`: +o in `#<machine>`, +h in `#bobiverse`. Simon: +o only while logged in to a
  NickServ account in `BOB_OP_ACCOUNTS` (a nick alone earns nothing). Re-applied on JOIN, MODE drift and a 60 s NAMES reconcile.
- Grants are hard-capped: max 3 per (channel, nick, mode) per 10 minutes, then one WARN. A grant that keeps being removed
  by someone else logs `removed by <actor> (not Jeeves)` - look for ChanServ AMODE / founder auto-modes, not a Jeeves bug.
- Repeated `GRANT +h` with fresh JOINs = the nick keeps reconnecting (see troubleshooting: ear restart loop), not a chair loop.

## Test procedures

- Unit/regression: `$env:PYTHONPATH="$PWD\scripts"; python -m pytest tests -q -p no:cacheprovider` (repo checkout only).
- Live command test as the bob ear: append `PRIVMSG #bobiverse :!help` (UTF-8, NO BOM, newline-terminated) to the ear's
  `home\outbox.txt` and read the chair's `cmd-trace.log` (time, nick, command, reply). Use dry-run forms (`!recycle dry-run`);
  never send a real `!recycle`, `!bored` or claim a job while testing.
- Webhooks: `GET /bob/v1/report` 200; `GET /bob/v1/jira` 200; `GET /bob/v1/intake/<id>` 404 = up; synthetic `ping` to
  `POST /bob/v1/git` (zen `jeeves-health-probe`) 204 with no announce.

## Known failures and fixes (learned in production)

| Symptom | Cause | Fix |
|---|---|---|
| `sasl-fail 904` / `433` loop, nick reserved | NickServ account password lost / wrong GUID | Oper `NickServ PASSWD <account> <the password file's value>` then restart that service; never mint a new password for a registered account |
| Installed skill paths show `...\scripts\` (triple dot) | `Sync-BobiverseAgentFolders` used plain Replace on `.\scripts\` | Rewrite only bare `.\scripts\` with `(?<!\.)` lookbehind (FR #1704 / PR #1709) |
| `Pack-BobiverseRelease.ps1` refused by WinPS 5.1 / weird first-char parse | Double-encoded UTF-8 BOM (`c3afc2bbc2bf`) | Re-save as UTF-8 (single BOM or no BOM per contract); do not Latin-1 round-trip BOM files |
| Config/JSON/ps1 "unexpected character" | UTF-8 BOM in a file that must have none (outbox, intake JSON) or missing BOM in a ps1 with non-ASCII | Outbox/JSON: write UTF-8 NO BOM. Read JSON with `utf-8-sig`. Keep BOM on existing `.ps1` |
| Ear restarts every 30-60 s, `+h`/`+o` re-granted each time | Watcher/tray kills an ear whose command line lacks `--host` | `Start-Bob.ps1 -IrcHost` passes `--host`; the MSI bakes `-IrcHost` into the NSSM service |
| Service points at an old tree after MSI | NSSM `Application` still the old path | Re-run `Install-<Product>.ps1` (or `nssm set <svc> Application ...`) |
| Ergo bounces on upgrade | `ergo.exe` hard-linked to the MSI payload | Component is Permanent+NeverOverwrite; installer runs `Repair-BobiverseErgoHardlink` (copy, rename aside, move into place; no stop) |
| Webhook 500/PermissionError, `digest.json*.tmp` | Digest writers collide / SYSTEM vs user ACL | Atomic write with unique tmp names + orphan cleanup is built in; fix ACL on the digest home for SYSTEM + the service user; do not delete `digest.json` |
| Roster empty / machine "not on the roster" | ChanServ `LIST` denied (oper lacks `chanreg`) or shop not `!register`ed | Check `chair-status chanserv-list=`; `!register <machine>`; `!resync` |
| `CryptUnprotectData failed` | Service runs as LocalSystem with an Admin-sealed identity | Set the service logon (`Complete-BobiverseServiceLogon.ps1`) |
| Unverified-WHOIS log line every minute | Verification pending for a nick | Throttled to once per 30 min; a persistent one means the nick has no NickServ account |
| Tray missing / duplicated | Old installers / session-0 start | One Start Menu folder `Bobiverse`; tray starts only in an interactive session (ONLOGON task / Startup shortcut) |
| `PropertyNotFoundException` / StrictMode `.Count` on `Sort-Object`/`Where-Object` | Pipeline of one item is a **scalar**, not an array | Wrap with `@(...)` before `.Count` / index ops (FR #1664 / PR #1672 / harvest #1689). Leave separate FreeGB capacity FRs open when they are distinct from the StrictMode bug |
| Agent transcript shows Ergo/SASL password after `nssm get` | `AppEnvironmentExtra` dumped raw (FR #147) | Print env **key names only** (split on first `=`); never paste AppEnvironmentExtra values into logs, filings, or chat |
| Self-update Apply hung / 0-byte MSI / mutex stuck | `Get-Asset` stalled on GitHub download without timeout | FR #1545: IWR TimeoutSec + curl `--max-time` fallback; throw → `download-failed` + mutex release (PR #1561). Check `...\update\<product>\update.log` |
| `Update-BobiverseService -Mode Check` -> `no-matching-asset` | GitHub release tag lacks `<product>-<ver>.msi` (+ `.sha256`) | Pack `-Product all` (or that product), `gh release upload` both files, then `Assert-BobiverseReleaseAssets.ps1 -Tag <tag>` (FR #2354) |
| Wrapper splat behaves oddly / wrong args | Script used automatic `$args` for splatting | Rename to an explicit array (e.g. `$launchArgs`) before `@splat` (PR #1588) |
| InstallRoot `VERSION` jumps after sync / disagrees with ARP | Sync copied a newer clone `VERSION` over the MSI stamp | ARP `DisplayVersion` wins; Sync heals InstallRoot to ARP and skips clone clobber (FR #1565 / #1589 / PR #1577) |
| Quiet MSI **1603** / `Assert-BobiverseInstallVersion` after RunInstall (FR #2948) | Install tree is a sparse work tree; `Copy-BobiverseVersion` resolved `src\VERSION` → stale `common\VERSION` when `RepoRoot==InstallRoot` and overwrote the MSI-laid `VERSION` | Forward `-MsiProductVersion` into `Copy-BobiverseVersion` (MSI wins); same-tree keep laid `VERSION` when it differs from git common. Product #2950. Do **not** park this playbook under `harvest` (MRB #2963 FAIL). |
| Quiet MSI upgrade loses heat-laid scripts/tools/skills (FR #2982) | Install tree dirty/behind; RunInstall copied stale git checkout over MSI payload; Sync composed again when VERSION already matched | When `-MsiProductVersion` is set, **SkipCopy** so heat-laid scripts/tools/skills win; `Sync-BobiverseFromRepo` must `sync-skip-stale-worktree` when ff/fetch did not tip the tree — VERSION equality alone is not enough (PR #2983). Same home as FR #2948: **fleet-ops**, never `harvest`. |
| Sync skips flat compose on a clean agent branch (FR #3622) | FR #2982 `$skipStaleCompose` treated every non-`already up to date`/`fast-forwarded` reason as MSI-stale, including clean `not main; fetched only` | Tip-ok also includes clean off-main `fetched only, work tree untouched` (no `; dirty`). WorkTree reason appends `; dirty` when porcelain is non-empty so dirty off-main still skips. Clean agent branch still composes into flat scripts (FR 020). |
| Quiet MSI **1603** / `node still missing after winget` under LocalSystem | Per-user WindowsApps `winget` alias unusable as SYSTEM; Node/git/python hard-failed | FR #1825: prefer pinned **nodejs.org** x64 MSI (`ALLUSERS=1` + sha256); soft-fail missing tools with `WARN tool-missing` so product MSI continues (PR #2019). Install machine-wide prereqs afterward if needed at runtime |
| UI MSI **1603** / ircBob left **Stopped** / seats gone after failed upgrade (FR #2564) | UI msiexec without `/l*v`; RunInstall removed the service then failed; no rollback start | Always `msiexec /i ... /l*v "%ProgramData%\Bobiverse\logs\msi-<product>-....log"`; read `install-*.log` / `recover-*.log` under the same folder; prefer self-update (`Restart-Service`) over parallel UI msiexec while Apply holds the mutex. Pack schedules RollbackRecover -> `Recover-BobiverseService`; Install scripts assert MSI ProductVersion vs VERSION and best-effort Start-Service on catch |
| Self-update Apply aborts at **robocopy >=8** / tag **blocked-loop-guard** / service left Stopped (FR #2563) | Backup threw on locked `.pytest_cache` / `peers.json`; MaxAttempts burned; no operator escape | Backup excludes volatile paths, retries once, logs failing paths; backup-only fails -> `backup-failed` **without** MaxAttempts burn + `Ensure-ServiceRunning`; `-ForceCheck` clears the tag (PR #2565). Prefer Restart-Service Apply over parallel UI msiexec |

## Harvested fleet-operation rules (skill records #1215-#1460)

- Honor `require_machine` pins literally: a DEV1/ionos operation must be assigned to that capable seat, never to a convenient but incapable worker. Hard pins beat `any`; do not derive a pin from an ambiguous title.
- On live Windows hosts, restart only the affected BobCallback task or `ircJeeves` service. Never restart BobIrcd/Ergo as a shortcut, and preserve queue/outbox evidence while recovering a callback or worker.
- For upgrades and resync, verify the installed VERSION, clean/main worktree, fetch result, service/task state, and endpoint health; record an ALERT when fetch/ff/worktree state is stale.
- After MSI, treat ARP `DisplayVersion` as VERSION truth for Sync heal; never let a newer repo/clone VERSION overwrite the MSI stamp (FR #1565 / harvest #1589).
- After FR #3289 `sync_from_repo` default-off, Sync-BobiverseFromRepo pytest that asserts heal/copy must set `BOBIVERSE_SYNC_FROM_REPO=1` (or config `sync_from_repo:true`) or the suite hits `sync-skip sync_from_repo=off`.
- MSI RunInstall (FR #2948): `Copy-BobiverseVersion` must honour `-MsiProductVersion` and must not clobber `InstallRoot\VERSION` with stale `common\VERSION` when `RepoRoot==InstallRoot` (PR #2950).
- MSI RunInstall (FR #2982): when `-MsiProductVersion` is set, SkipCopy so heat-laid scripts/tools/skills win; Sync must `sync-skip-stale-worktree` when ff/fetch did not tip the install tree — VERSION equality alone is not enough (PR #2983). FR #3622: clean agent-branch `fetched only` still composes; only dirty/ff-blocked/fetch-fail skip.
- Quiet MSI bootstrap under SYSTEM: do not rely on per-user WindowsApps winget; prefer pinned nodejs.org MSI for Node and soft-fail git/python/node so install does not 1603 (FR #1825 / harvest #2020 / PR #2019).
- UI MSI upgrades (FR #2564): require `/l*v` under `%ProgramData%\Bobiverse\logs`; never leave ircBob/Airc Stopped after a failed RunInstall — rollback recover + Install catch Start-Service; assert InstallRoot VERSION matches MSI ProductVersion.
- Self-update backup (FR #2563): robocopy >=8 soft-fails without MaxAttempts burn; Ensure-ServiceRunning; -ForceCheck clears blocked-loop-guard (PR #2565).

## Harvest digest (lessons audit 2026-10-06)

Generalised from 32 harvested lessons that never reached this book (audit for FR #2705). The per-lesson table is in `common/docs/harvest-lessons-audit-2026-10-06.md`.

- **WinPS 5.1 / StrictMode:** never read optional properties bare (`$ex.Response`, `$r.url`); gate them through `PSObject.Properties`. Wrap with `@()` before `.Count`. Stringify git stderr before Out-Host and check `$LASTEXITCODE`. Keep CA/MSI scripts ASCII and never bind a parameter named `$Home`. `Set-Content -Encoding utf8` writes a BOM, so use `UTF8Encoding($false)`. Start-Process needs distinct stdout/stderr redirect paths and an unquoted `--root` in ArgumentList. Drain stderr concurrently with stdout. Never splat the automatic `$args`. (15 lessons: harvest #2159, #2047, #2006, 13 held intake rows)
- **MSI / NSSM / release:** scripts on main do not change shipped MSIs: re-Pack, replace the release assets, run Assert-BobiverseReleaseAssets, then Apply. Graceful services need an explicit `AppExit 0=Restart`. Stamp VERSION only after ARP matches. Uninstall needs a deferred RunUninstall before RemoveFiles and must keep the ConsoleHome secrets. Upgrades read the existing NSSM AppParameters before defaults. WiX deferred CAs need Secure public properties expanded in the immediate SetInstallCmd. A dirty install tree blocks ff, so overlay the origin updater after the scripts compose. (9 lessons: harvest #1639, #1499, #1492, #1489, #1478, #112 +2 more, 1 held intake row)
- **Crash reporting:** probes use `exe=probe`, `do-not-file` or `probe-shape-only` markers so intake and the spool flush skip them (C# CrashHook mirrors `should_skip_report`). Real crashes spool under LOCALAPPDATA and are never dropped. `crash:` RETEST receipts are closed citing the covering PR, not implemented. Product `main()` under pytest must not install the crash hook. **Opt-out (FR #3291 / C# parity FR #3328):** env `BOB_CRASH_REPORT=0|local-only|no-log-tail`, `<InstallRoot>\config\crash-report.json` (`enabled`/`mode`/`include_log_tail`), MSI `BOBIVERSE_CRASH_REPORT=0` (kept across upgrades). When off/local-only: spool only, no intake/`gh` — Python `crash_report` and C# `CrashHook` (`bob-about`/`bob-status`/`bob-tray`) both honour the same policy. Airc `shell=off` defaults crash-report off. **FR #3452:** `local_only` / `error=local_only` spool stamps are dropped on later `flush_spool`/`FlushSpool` even when send is re-enabled — never POST opt-out payloads to intake (false-positive twins #3452/#3453). Tests that deliberately raise under opt-out must isolate `BOB_CRASH_SPOOL`. (8 lessons + FR #3291 + FR #3328 + FR #3452)

## Harvested lessons (intake)

- Harvest-lesson FAIL-supersede when bobiverse-fleet-ops already has FR #3622 Sync tip-ok / skipStaleCompose product table+digest; do not merge weaker Harvested lessons

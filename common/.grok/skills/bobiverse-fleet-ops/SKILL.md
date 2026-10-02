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
## Fleet model (what talks to what)

- **Ergo** IRC server (service `BobIrcd`, tree `<ai root>\ergo`, TLS :6697 public, plaintext :6667 loopback). Runs on exactly one box.
  NEVER edit `ircd.yaml`, never restart `BobIrcd` as part of a fix for something else.
- **Jeeves** chair (service `ircJeeves`, nick `Jeeves`, `irc_agent.py --chair`): channel privileges, roster, queue, commands,
  digest, webhooks. **Bob ear** (service `ircBob`, nick `Bob-<machine>`, SASL account `bob-<machine>`): one per box, JOINs
  `#bobiverse` + `#<machine>`. **Airc** console (service `Airc`, nick `<machine>_console`): remote shell over PRIVMSG.
- **bobcallback** (scheduled task `BobCallback`, SYSTEM, `127.0.0.1:7700`): receives `/bob/v1/report|digest|git|intake|jira`.
  Public URL `https://irc.ntsa.uk/bob/v1/...` is an IIS URL-Rewrite site (`irc-ntsa`) in front of it.
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
- Self-update: on every service start `Update-BobiverseService.ps1` asks GitHub releases/latest (no token), verifies the
  `.sha256`, stops ONLY that service, backs up the tree (`<ProgramData>\bobiverse\update\<product>\backup`), runs the MSI, refreshes
  skills, starts. Any failure = automatic rollback + loop guard. Log: `...\update\<product>\update.log`.
  Opt out: `BOBIVERSE_NO_UPDATE=1` or `<InstallRoot>\config\autoupdate.disabled`.
- Rollback by hand: stop the one service, restore the newest backup `tree\` over `<InstallRoot>`, re-run
  `Install-<Product>.ps1 -SkipCopy`, start. Never touch `ergo\`.

## Hotpatch safely (the only approved way to test a fix on a live box)

1. **Back up first**: `Copy-Item <InstallRoot> <InstallRoot>-backup-<yyyyMMdd-HHmmss> -Recurse`.
2. Copy only the changed `scripts\*.py|*.ps1` over the live files (keep BOM/CRLF; compile-check Python, parse-check PowerShell).
3. **Restart ONLY that service** (`Restart-Service ircJeeves`). Never `BobIrcd`/Ergo, never edit `ircd.yaml`, never kill or
   restart seats/agents, never `Stop-Process` broad names (`powershell`, `python`).
4. Verify in the log, then run the command/behaviour tests below. Record what you changed (path + hash).
5. PowerShell only on Windows boxes; never wrap a command in `powershell -Command`; never print a secret.
6. Do not rebuild/release/bump the version unless the owner says so.

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
| Config/JSON/ps1 "unexpected character" | UTF-8 BOM in a file that must have none (outbox, intake JSON) or missing BOM in a ps1 with non-ASCII | Outbox/JSON: write UTF-8 NO BOM. Read JSON with `utf-8-sig`. Keep BOM on existing `.ps1` |
| Ear restarts every 30-60 s, `+h`/`+o` re-granted each time | Watcher/tray kills an ear whose command line lacks `--host` | `Start-Bob.ps1 -IrcHost` passes `--host`; the MSI bakes `-IrcHost` into the NSSM service |
| Service points at an old tree after MSI | NSSM `Application` still the old path | Re-run `Install-<Product>.ps1` (or `nssm set <svc> Application ...`) |
| Ergo bounces on upgrade | `ergo.exe` hard-linked to the MSI payload | Component is Permanent+NeverOverwrite; installer runs `Repair-BobiverseErgoHardlink` (copy, rename aside, move into place; no stop) |
| Webhook 500/PermissionError, `digest.json*.tmp` | Digest writers collide / SYSTEM vs user ACL | Atomic write with unique tmp names + orphan cleanup is built in; fix ACL on the digest home for SYSTEM + the service user; do not delete `digest.json` |
| Roster empty / machine "not on the roster" | ChanServ `LIST` denied (oper lacks `chanreg`) or shop not `!register`ed | Check `chair-status chanserv-list=`; `!register <machine>`; `!resync` |
| `CryptUnprotectData failed` | Service runs as LocalSystem with an Admin-sealed identity | Set the service logon (`Complete-BobiverseServiceLogon.ps1`) |
| Unverified-WHOIS log line every minute | Verification pending for a nick | Throttled to once per 30 min; a persistent one means the nick has no NickServ account |
| Tray missing / duplicated | Old installers / session-0 start | One Start Menu folder `Bobiverse`; tray starts only in an interactive session (ONLOGON task / Startup shortcut) |

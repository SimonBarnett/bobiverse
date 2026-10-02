---
name: bobiverse-bob
description: >
  Use and maintain the ircBob ear, tray and shop on a fleet box. Architecture, paths, channels, config, logs, tray, install/upgrade/hotpatch. Use in C:\ai\bob or for the Bob service, tray restart, ear debugging, SASL/NickServ, or /bobiverse-bob.
---

# bobiverse-bob

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

Foundation: `bobiverse-fleet-ops` (shared ops/hotpatch/health) and `harvest` -> https://github.com/SimonBarnett/bobiverse

## Architecture

`ircBob` runs `Start-Bob.ps1 -> irc_agent.py --nick Bob-<machine> --home <home> --channel #bobiverse,#<machine> --host <irc host>`
(NSSM). The ear is the box's presence on IRC: it keeps the shop channel, reports status to the digest, executes `!recycle`
for its own machine, drains `home\outbox.txt`, and hosts the talk seats. The **TipForm tray** is an interactive companion
(not a service, not a `BobFleet-*` task). Digest POSTs need no secret (roster-gated by Jeeves).

| Piece | Where |
|---|---|
| Install root | `C:\ai\bob` (`scripts\`, `tools\` TipForm, `src\` BobBridge, `assets\bob-systray.ico`, `config\`, `logs\`, `.grok\skills\`, `PIN.txt`, `VERSION`) |
| Ear home | `C:\ai\bob\home` (LocalSystem) else `~\.bobiverse`; `outbox.txt` (+`.pos`), `irc.log` (with `BOB_IRC_DEBUG=1`), `nickserv.password`, `accounts.json`, `digest.json` |
| Logs | `C:\ai\bob\logs\stdout.log` / `stderr.log` (rotated `ircBob-*` files) |
| IRC | channels `#bobiverse` + `#<machine>`; nick `Bob-<machine>`; SASL user `bob-<machine>`; host passed explicitly with `--host` (Start-Bob `-IrcHost`, default `irc.ntsa.uk`) |
| Config | `config\ergo.password` (server PASS), `home\nickserv.password` (SASL), `service.password`/`BOBIVERSE_SERVICE_PASSWORD` (DPAPI logon) |
| Tray | `scripts\Start-BobTray.ps1 -> tools\Start-BobFleetTray.ps1`; HKCU `Run\BobiverseTray`; per-user Startup shortcut; quiet MSI uses the ONLOGON `/IT` task `BobiverseTray` |
| Start Menu | ONE all-users folder `Bobiverse`: Bobiverse Tray, Restart ircBob, Bob Services, Logs, Skill books, Agent guide (all systray icon) |

## Roles

- After Jeeves `!register <machine>` the ear is +o in `#<machine>` and +h in `#bobiverse`. Agents (`<machine>-<pid>`) JOIN the shop only.
- The ear nick `Bob-<machine>` is ALSO an authorized principal for Jeeves ops commands (`!focus`, `!ignore`, `!sweep`, `!resync`, `!recycle`).
- Product Sync/ff and self-update run on **ircBob start** only; the tray never updates the tree.

## Install, upgrade, rollback, hotpatch

See `bobiverse-fleet-ops`. Bob specifics: hotpatch = back up `C:\ai\bob`, copy changed `scripts\*`, `Restart-Service ircBob` (or
`Restart-BobEar.ps1`, which announces the departure first). Do not kill seats/agents or the tray to apply a patch. `Start-Bob.ps1`
must pass `--host` or the watcher/tray treats the ear as foreign and kills it (restart loop).

## Do not

- Self-REGISTER the shop with ChanServ (Jeeves `!register` only); mint a fresh NickServ GUID for a registered `bob-*` account.
- Double-start the ear when `ircBob` is Running; kill broad `powershell.exe`/`python.exe`; stamp UAT; invent an Ergo PASS.

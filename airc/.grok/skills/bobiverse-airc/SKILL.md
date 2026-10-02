---
name: bobiverse-airc
description: >
  Maintain the Airc console service ({machine}_console). Architecture, paths, shop vs lobby, config, logs, install/upgrade/hotpatch. Use in C:\ai\airc or for Airc MSI, remote PRIVMSG shell, AircConsole leftovers, or /bobiverse-airc.
---

# bobiverse-airc

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

Service **`Airc`** (NSSM, tree `C:\ai\airc`) runs the Airc console: an IRC client with nick **`<machine>_console`** that executes
short commands sent to it by authorized fleet ears (`bob-*`) and replies by PRIVMSG. It JOINs the shop `#<machine>` when ChanServ
has it registered (`shop-mode=auto` probes `INFO #<machine>`), otherwise the domain/workgroup lobby `#<domain|workgroup>`.

| Piece | Where |
|---|---|
| Install root | `C:\ai\airc` (`scripts\`, `config\`, `logs\`, `assets\bob-systray.ico`, `.grok\skills\`, `VERSION`) |
| Console home (identity, NickServ GUID `console.password`, logs) | `%USERPROFILE%\.airc`; under quiet MSI/LocalSystem prefer `C:\Users\Administrator\.airc`, else `C:\ai\airc\home` - NEVER `C:\Users\Default\.airc` (orphans the NickServ GUID) |
| Config | `C:\ai\airc\config\ergo.password` (server PASS) |
| Logs | `C:\ai\airc\logs\*.log`, `<console home>\*.log`, `airc-console-service.log` under the user's `.grok\long-running-background-tasks` |
| IRC | SASL on by default for the reserved `<machine>_console` nick (before NICK) |
| Start Menu | ONE all-users folder `Bobiverse`: Restart Airc, Bob Services, Logs (airc), Skill books (airc), Agent guide (airc) - systray icon |

**Airc vs AircConsole:** bobiverse `Airc` (`C:\ai\airc`) has a distinct UpgradeCode from agentic_irc `AircConsole` (`C:\ai\airc-console`).
One console per box: `Install-Airc` removes a leftover `AircConsole` service from the SCM.

## Install, upgrade, rollback, hotpatch

See `bobiverse-fleet-ops`. Airc specifics: after the MSI, place `config\ergo.password` (or `~\.grok\ergo\connect.password`); re-run
`Install-Airc.cmd -MachineId <id>` if NSSM still points at an old tree. Self-update on start (`Update-BobiverseService.ps1`;
`Sync-BobiverseFromRepo.ps1` when a clone exists). Hotpatch = back up `C:\ai\airc`, copy the changed scripts, `Restart-Service Airc`
ONLY. Killing broad `powershell.exe` on the box can take down Airc's own host process - target PIDs; afterwards `Restart-Service Airc`
until `<machine>_console` is visible on IRC again.

## Do not

- Run `Airc` and `AircConsole` together; invent an Ergo PASS; stamp UAT; send multi-line PowerShell in one PRIVMSG.

---
name: bobiverse-airc-commands
description: >
  Airc console command reference - PRIVMSG remote shell via {machine}_console, allowlist, safe diagnostics, staging scripts. Use when sending commands to a box through Airc.
---

# bobiverse-airc-commands

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

## Remote shell protocol (FR #75)

An authorized sender (`bob-*` ear) PRIVMSGs the console:

```text
PRIVMSG <machine>_console :Get-Service Airc
PRIVMSG <machine>_console :cmd: sc query ircJeeves
PRIVMSG <machine>_console :psb64:<base64>
PRIVMSG <machine>_console :STATUS
```

- Default is **PowerShell 5.1** (`-NoProfile`) once FR #75 is deployed; `cmd:` uses COMSPEC; `psb64:` is EncodedCommand.
- Replies (FR #75): `out id=… seq=…`, `err id=… seq=…`, then `DONE id=… exit=…` (chunked ~350).
- Allowlist: `bob-*` ears may always PRIVMSG `*_console`. Nothing else is authorized.
- Driving-box helper: `scripts\Invoke-AircRemote.ps1` (FR #76) builds bodies, PUT chunks+sha256, redacts secrets, optional `-Outbox`.
- PUT/RUN/JOB server-side: FR #78. UPDATE safety: FR #77 + `Update-BobiverseService.ps1` detached Apply.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-AircRemote.ps1 -SelfTest
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-AircRemote.ps1 `
  -MachineId <id> -Action Command -Text 'Write-Output ping' -Outbox <ear-outbox>
```

## Safe diagnostic commands

`Get-Service Airc`, `cmd: sc query <svc>`, `Get-Content <ai root>\<product>\VERSION`, `Get-ChildItem <ai root>\<product>\logs`.
Do NOT: kill broad `powershell.exe`/`python.exe`, `sc stop BobIrcd`, edit Ergo files, print secrets.

## Verify the console

`Get-Service Airc`; log shows `chanserv-info status=registered` and `joined #<machine> as <machine>_console`.

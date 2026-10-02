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

## Remote shell protocol (today)

An authorized sender (`bob-*` ear) PRIVMSGs the console:

```text
PRIVMSG <machine>_console :sc query ircJeeves
```

- The command runs in **cmd.exe** under the Airc service account (often SYSTEM); the reply comes back as PRIVMSG lines from
  `<machine>_console` (visible in the sender's `irc.log` with `BOB_IRC_DEBUG=1`).
- Keep each command SHORT (IRC line limit). Multi-line PowerShell does not survive: stage a script with
  `irm <raw-url> -OutFile C:\ai\drop\x.ps1` then `powershell -File C:\ai\drop\x.ps1`.
- Allowlist: `bob-*` ears may always PRIVMSG `*_console`. Nothing else is authorized.
- Planned extension (not shipped): PowerShell default + PUT/RUN - see `docs/airc-remote-control.md`.

## Safe diagnostic commands

`sc query <svc>`, `sc qc <svc>`, `type C:\ai\<product>\VERSION`, `dir C:\ai\<product>\logs`, `tasklist /fi "imagename eq python.exe"`.
Do NOT: kill broad `powershell.exe`/`python.exe`, `sc stop BobIrcd`, edit Ergo files, print secrets.

## Verify the console

`Get-Service Airc`; log shows `chanserv-info status=registered` and `joined #<machine> as <machine>_console`.

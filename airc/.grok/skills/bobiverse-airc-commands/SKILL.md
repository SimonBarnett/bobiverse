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

An authorized sender (operators list / seeded `bob-<machine>` ear) PRIVMSGs the console:

```text
PRIVMSG <machine>_console :Get-Service Airc
PRIVMSG <machine>_console :cmd: sc query ircJeeves
PRIVMSG <machine>_console :psb64:<base64>
```

- Default is **PowerShell 5.1** (`-NoProfile`); `cmd:` uses COMSPEC; `psb64:` is `-EncodedCommand` (UTF-16LE or UTF-8 payload).
- Replies are Query-only: `out id=… seq=…`, `err id=… seq=…`, then `DONE id=… exit=…`. Long lines are chunked (~350 chars).
- Allowlist: nick must be in operators (installer seeds `bob-<machine>`); arbitrary `bob-*` is **not** auth (FR #3286). With `--require-account` / `--accounts`, SASL/NickServ account must match too.
- PUT/RUN/JOB/UPDATE are separate FRs — see `docs/airc-remote-control.md`.

## Safe diagnostic commands

`sc query <svc>`, `sc qc <svc>`, `type <ai root>\<product>\VERSION`, `dir <ai root>\<product>\logs`, `tasklist /fi "imagename eq python.exe"`.
Do NOT: kill broad `powershell.exe`/`python.exe`, `sc stop BobIrcd`, edit Ergo files, print secrets.

## Verify the console

`Get-Service Airc`; log shows `chanserv-info status=registered` and `joined #<machine> as <machine>_console`.

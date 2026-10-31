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
- PUT/RUN/JOB/UPDATE are separate FRs - see `docs/airc-remote-control.md`.
- **VERSION (FR #5281):** same auth as STATUS (`+o/+h`+). `PRIVMSG {mid}_console :id=<8hex> VERSION` replies `out id= seq=1 VERSION machine=... airc_ver=...` then `DONE id= exit=0`. Reads `<ai root>\\airc\\VERSION` only (missing -> `-`; no ARP). Allowed when `shell=off` / `jobs=off` like STATUS. STATUS still returns the bob/airc/jeeves aggregate.

## Safe diagnostic commands

`sc query <svc>`, `sc qc <svc>`, `type <ai root>\<product>\VERSION`, `dir <ai root>\<product>\logs`, `tasklist /fi "imagename eq python.exe"`.
Do NOT: kill broad `powershell.exe`/`python.exe`, `sc stop BobIrcd`, edit Ergo files, print secrets.

## Verify the console

`Get-Service Airc`; log shows `chanserv-info status=registered` and `joined #<machine> as <machine>_console`.

## UPDATE and VERSION (FR #5282)

Prefer remote **`UPDATE airc`** over free-form `msiexec` / `Restart-Service Airc` (killing the console mid-playbook drops the transport).

```text
PRIVMSG {mid}_console :UPDATE airc
PRIVMSG {mid}_console :UPDATE airc 1.0.9
PRIVMSG {mid}_console :id=c25bd00e VERSION
```

- **Latest vs pin:** bare `UPDATE airc` takes the latest GitHub Release MSI. `UPDATE airc <ver>` pins `-TargetVersion` (FR #5280 / FR #77).
- **Restart contract (Refs #5277):** after Apply, expect Airc Running and `{mid}_console` to answer again within a **120s** reconnect budget without manual repair. If it does not, file intake; do not invent a second msiexec.
- **Failure intake (FR #5279):** each Apply/Check failure class (`download-failed`, `msiexec-exit`, `msiexec-timeout`, `stop-failed`, `backup-failed`, `spawn-failed`, `updater-missing`, `asset-url-rejected`, ...) files one `kind:issue` on `SimonBarnett/bobiverse`. `idempotency_key` = `airc-update-fail|{machine}|{product}|{tag}|{result}` so retries do not twin-flood. Title/body are redacted.
- **VERSION (FR #5281):** same auth as STATUS. Reply is `out id= seq=1 VERSION machine=... airc_ver=...` then `DONE id= exit=0`. Reads `<ai root>\\airc\\VERSION` only (missing -> `-`; no ARP). Allowed when `shell=off` / `jobs=off`.

See `docs/airc-remote-control.md` and `bobiverse-airc-troubleshooting`.


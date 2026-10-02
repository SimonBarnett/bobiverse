# Airc remote control (protocol sketch)

See **[feature-request-airc-remote-control-2026-10-01.md](./feature-request-airc-remote-control-2026-10-01.md)** for LOCKED success metrics.
Ops: **[airc-ops.md](./airc-ops.md)**. Driving-box helper: **`scripts/Invoke-AircRemote.ps1`** (FR #76).

## Today (FR #75 shell ergonomics shipped; PUT/RUN/UPDATE still pending)

Authenticated PRIVMSG to `{machine}_console` runs a **oneshot** job (default **PowerShell 5.1** `-NoProfile -NonInteractive -EncodedCommand`). Replies are Query-only:

```text
out id=<job> seq=<n> <chunk>
err id=<job> seq=<n> <chunk>
DONE id=<job> exit=<code>
```

Long lines are chunked to ~350 payload chars (no silent 400 clip). `cmd:` uses COMSPEC `/d /c`; `psb64:` accepts UTF-16LE native or UTF-8 script bytes.

```text
PRIVMSG marchhare_console :Write-Output $PSVersionTable.PSVersion
PRIVMSG marchhare_console :cmd: echo %COMSPEC%
PRIVMSG marchhare_console :psb64:<utf16le-or-utf8-base64>
```

## Helper (FR #76)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-AircRemote.ps1 -SelfTest
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Invoke-AircRemote.ps1 `
  -MachineId <id> -Action Status|Command|Cmd|Psb64|Put|Run|Job|Cancel|Update `
  [-Text ...] [-Path ...] [-LocalFile ...] [-Outbox ...] [-WhatIf]
```

Builds IRC-safe bodies, UTF-16LE `psb64`, PUT chunks + SHA-256, sandbox path checks, reply correlation (`DONE id= exit=`), retries, and secret redaction. Server-side PUT/RUN/STATUS acceptance is FR #78; shell DONE framing is FR #75.

## Target verbs

| Verb | Purpose |
|------|---------|
| plain line | PowerShell (default, FR #75) |
| `cmd: …` | COMSPEC escape hatch |
| `psb64:<b64>` | `powershell -EncodedCommand` |
| `STATUS` | Airc Running + VERSION files (bob/airc/jeeves) |
| `PUT` + `CHUNK` + `PUTEND` | Write file (base64 seq + sha256) |
| `RUN path` | Execute; end with `DONE id=… exit=…` |
| `JOB` / `CANCEL` | Job lifecycle |
| `UPDATE airc\|bob\|jeeves [ver]` | Detached `Update-BobiverseService.ps1` path (FR #77) |

## Encoding policy

- Short ops: **plain text** (readable in Halloy / irc.log).
- Scripts / `$` / spaces: **base64** (`psb64` or PUT).
- Secrets: **never** clear IRC — local files or agentic-file SEAL; helper redacts transcripts.
- Large logs/MSI: HTTPS allowlist or path drop — IRC is control plane.

## CAST IRON ops notes

- Do not inline `msiexec` **airc** over the live console transport — use detached `Update-BobiverseService.ps1` Apply.
- Prefer `start /wait msiexec` and install **airc last/alone**.
- LocalSystem ConsoleHome must not be `C:\Users\Default\.airc` (see post-install §8b).
- Reserved nick + wrong GUID → oper `PASSWD {machine}_console <guid>` then restart Airc.

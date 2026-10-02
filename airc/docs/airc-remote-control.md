# Airc remote control (protocol sketch)

See **[feature-request-airc-remote-control-2026-10-01.md](./feature-request-airc-remote-control-2026-10-01.md)** for LOCKED success metrics.
Ops: **[airc-ops.md](./airc-ops.md)**. Driving-box helper: **`scripts/Invoke-AircRemote.ps1`** (FR #76).

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
- LocalSystem ConsoleHome must not be `C:\Users\Default\.airc`.
- Reserved nick + wrong GUID → oper `PASSWD {machine}_console <guid>` then restart Airc.

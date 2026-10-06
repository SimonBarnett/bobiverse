# Airc remote control (protocol sketch)

See **[feature-request-airc-remote-control-2026-10-01.md](./feature-request-airc-remote-control-2026-10-01.md)** for LOCKED success metrics.

## Today (v0.1.x)

Authenticated PRIVMSG to `{machine}_console` runs PowerShell (or `cmd:` / `psb64:`) and returns Query lines `out`/`err`/`DONE id=… exit=…`. The bob ear appends those to `<bob home>\airc-replies.jsonl` (FR #1546). `Invoke-AircRemote.ps1 -Outbox … -ReplyFile …` prefixes `id=<corr>` and waits for matching DONE (non-zero exit on timeout).

Concurrent Commands on the same Query are **queued** (FR #2632)

On service stop / session interrupt, DONE for every in-flight and pending shell id is flushed **before** the IRC socket closes (FR #2640); late worker emits enqueue-only so stop never `sendall`s after close (avoids WinError 10038 + lost DONE).: one shell in flight plus a short pending list; each job still emits its own DONE. A full queue fail-closes with `busy: prior shell still emitting` + `DONE exit=1` (FR #2612: no hang). `Invoke-AircRemote` retries that busy reply within `-MaxRetries` / `-TimeoutSec` when `-JobId` was not pinned (compat with older airc).

```text
PRIVMSG marchhare_console :id=aabbccdd Write-Output ping
PRIVMSG marchhare_console :id=aabbccdd cmd: echo %COMSPEC%
```

## Target verbs (FR)

| Verb | Purpose |
|------|---------|
| `STATUS` | Airc Running + VERSION files (bob/airc/jeeves); replies as `out id= seq=` then `DONE` (FR #2575) |
| plain line | PowerShell (default); UTF-8 `$OutputEncoding` wrap so StdOut keeps Greek/CJK (FR #2580) |
| `cmd: …` | COMSPEC escape hatch (`chcp 65001` prefixed, FR #2580) |
| `psb64:<b64>` | `powershell -EncodedCommand` (same UTF-8 wrap) |
| `PUT path` + chunks | Write file (base64 seq) |
| `RUN path` | Execute; end with `DONE id=… exit=…` |
| `GET path` | hash/size + head/tail |
| `UPDATE airc\|bob\|jeeves [ver]` | Allowlisted GitHub Release MSI via detached `Update-BobiverseService.ps1` (FR #77) |

## UPDATE (FR #77) — shipped

Authorized PRIVMSG only (`bob-*` / operators):

```text
PRIVMSG marchhare_console :UPDATE airc
PRIVMSG marchhare_console :UPDATE airc 0.1.20
```

- Schedules **Check** mode of `Update-BobiverseService.ps1` with `-ForceCheck` (and optional `-TargetVersion`).
- Detached helper (scheduled task / WMI) runs **Apply** later; the live airc process never invokes `msiexec`.
- Reply (`UPDATE accepted status=scheduled …` or `UPDATE skipped-pending …`) is sent **before** the transport is stopped.
- Assets must be `https://github.com/SimonBarnett/bobiverse/releases/download/...`; foreign URLs are rejected.
- Pending / loop-guard / rollback / sha256 mismatch behaviour is owned by the updater (same as service-start self-update).
- Machine id: explicit `-MachineId`, then `AIRC_CONSOLE_MACHINE` / `BOB_MACHINE_ID`; hostname fallback must be conscious (Start-AircConsole warns).

## Encoding policy

- Short ops: **plain text** (readable in Halloy / irc.log).
- Scripts / `$` / spaces: **base64** (`psb64` or PUT).
- Secrets: **never** clear IRC — local files or agentic-file SEAL.
- Large logs/MSI: HTTPS allowlist or path drop — IRC is control plane.

## CAST IRON ops notes

- Prefer `UPDATE airc` over free-form `msiexec` / `Restart-Service Airc` mid-playbook — the transport dies if you kill airc yourself.
- LocalSystem ConsoleHome must not be `C:\Users\Default\.airc` (see post-install §8b).
- Reserved nick + wrong GUID → oper `PASSWD {machine}_console <guid>` then restart Airc.

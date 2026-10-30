# Airc remote control (protocol sketch)

See **[feature-request-airc-remote-control-2026-10-01.md](./feature-request-airc-remote-control-2026-10-01.md)** for LOCKED success metrics.

## Today (v0.1.x)

Authenticated PRIVMSG to `{machine}_console` runs PowerShell (or `cmd:` / `psb64:`) and returns Query lines `out`/`err`/`DONE id=… exit=…`. The bob ear appends those to `<bob home>\airc-replies.jsonl` (FR #1546). `Invoke-AircRemote.ps1 -Outbox … -ReplyFile …` prefixes `id=<corr>` and waits for matching DONE (non-zero exit on timeout).

**FR #4796 (driver pacing):** multi-line outbox bursts (`-Action Put` chunks) sleep `-OutboxPaceMs` (default 800, matches bob ear `FLOOD_S`) between lines. After a large reply (`>= -BurstReplyThreshold` out/err lines), `Invoke-AircRemote` sleeps `-PostBurstCoolMs` (default 2000) before returning so sequential Commands do not stack under Ergo fakelag. The bob ear also uses `CONSOLE_OUTBOX_FLOOD_S` (default 1.5s, env `BOB_CONSOLE_OUTBOX_FLOOD_S`) when draining `PRIVMSG *_console` from `home\outbox.txt`. Console reply token-bucket / truncate is FR #4790.

Concurrent Commands on the same Query are **queued** (FR #2632): one shell in flight plus a short pending list; each job still emits its own DONE. A full queue fail-closes with `busy: prior shell still emitting` + `DONE exit=1` (FR #2612: no hang). `Invoke-AircRemote` retries that busy reply within `-MaxRetries` / `-TimeoutSec` when `-JobId` was not pinned (compat with older airc).

**Hung shell recovery (FR #5211):** capture uses regular temporary files rather than waiting for pipe EOF from descendants. The shell deadline returns partial output plus `DONE exit=124`; UTF-16 (BOM or recognizable NUL pattern) is decoded and other invalid bytes are replaced. Output/encoding faults must not prevent the terminal DONE attempt or the next queued command. `CANCEL id=<shell-id>` from the same authorized Query signals the active shell and clears that Query's pending shells; each cancelled id gets `DONE exit=130`. CANCEL retains the exec authorization and shell/jobs capability gates; unknown shell ids still use the existing uploaded-job CANCEL protocol. STATUS is handled independently of the shell queue.

On an older client, if STATUS times out after partial shell output and no DONE, restart **only `Airc` on the client** using local or another authorized management access: `Restart-Service Airc`. The unresponsive IRC console cannot reliably restart itself. Verify STATUS after restart; do not restart `ircBob`, seats, tray or `BobIrcd`/Ergo. The `??` output alone does not establish the incident's root cause; check service logs for disconnects, stop/restart and encoding errors without printing sensitive file contents.

On service stop / session interrupt, DONE for every in-flight and pending shell id is flushed **before** the IRC socket closes (FR #2640 / #2649) with **no per-line FLOOD_S delay** so SCM cannot kill the socket between err and DONE; `_stop_flushed` skips a second finally drain after sock=None. Late worker emits enqueue-only so stop never `sendall`s after close.

```text
PRIVMSG marchhare_console :id=aabbccdd Write-Output ping
PRIVMSG marchhare_console :id=aabbccdd cmd: echo %COMSPEC%
```

## Target verbs (FR)

| Verb | Purpose |
|------|---------|
| `STATUS` | Airc Running + VERSION files (bob/airc/jeeves); replies as `out id= seq=` then `DONE` (FR #2575) |
| plain line | PowerShell (default); UTF-8 `$OutputEncoding` wrap so StdOut keeps Greek/CJK (FR #2580); `$ProgressPreference=SilentlyContinue` so StdErr stays free of CLIXML progress noise (FR #2641); terminating / `Write-Error` StdErr is decoded from CLIXML to plain text with user-relative `At line:` (FR #2910 / #2918) |
| `cmd: …` | COMSPEC escape hatch (`chcp 65001` prefixed, FR #2580); trailing `\` paths like `cmd: dir C:\` work (FR #3773: `/d /s /c` string cmdline, not list2cmdline) |
| `psb64:<b64>` | `powershell -EncodedCommand` (same UTF-8 wrap) |
| `PUT path` + chunks | Write file (base64 seq) |
| `RUN path` | Execute; end with `DONE id=… exit=…` |
| `GET path` | hash/size + head (80 chars). Does not send the file. |
| `GET path fetch=chunk` then `GETCHUNK id seq` | FR #4795 outbound fetch. Open returns bytes/sha256/seqs only. Each GETCHUNK returns one <=300-byte raw chunk. The next GETCHUNK is the ack; the console never pushes the following chunk. |
| `UPDATE airc\|bob\|jeeves [ver]` | Allowlisted GitHub Release MSI via detached `Update-BobiverseService.ps1` (FR #77) |

## UPDATE (FR #77) — shipped

Authorized PRIVMSG only (operators list; `bob-<machine>` when seeded — FR #3286, never arbitrary `bob-*`):

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

## Large replies / flood (FR #4790)

Shell replies are capped at `SHELL_REPLY_MAX_IRC_LINES` IRC `out`/`err` lines. Oversized output ends with `err ... output truncated, N lines omitted; CONT id=<job> (FR #4794); file fetch / PUT (FR #4790); DCCLISTEN (FR #5003)` then `DONE`. Send `CONT id=<job>` or `RESUME id=<job>` (optional `offset=N`) to fetch the next page without re-running the command.

**FR #5003 / #5008 bulk DCC:** for large listings, prefer a reverse TCP/TLS stream instead of IRC lines. Before (or with) the command, the caller may PRIVMSG:

`DCCLISTEN id=<job> host=<ip> port=<n> token=<hex> [tls=0|1] [relay=<host:port>]`

`tls=` defaults to **1** (FR #5008). When the shell output exceeds the bulk threshold and a matching listen offer exists, the console connects **out** to that host:port (or to `relay=` when both sides are NAT'd), sends `token\n` + `u32be length` + body + `sha256\n` (TLS-wrapped when `tls=1`), and replies on IRC with a short hint plus `DONE id=... exit=... bytes=N sha256=H via=dcc` (no body flood). If the handshake fails within a few seconds, it falls back to the IRC CONT path and emits `err ... dcc failed: ...; falling back to IRC` with the **next unused seq** immediately before `DONE` (FR #5065) — never `err seq=1` plus `out seq=1` (ConvertFrom-AircRemoteReply fail-closes on duplicate seq). Live MarchHare retest (FR #5069, tip `91648f9b`, job `b6782a52`): forced `DCCLISTEN` to closed port 1 yielded `err seq=50` then `DONE exit=0` with 50 unique seqs; `ConvertFrom-AircRemoteReply` parsed cleanly (evidence under `airc/docs/evidence/fr-5069-dcc-fallback-live-retest/`). `Invoke-AircRemote` helpers: `New-AircDccListenOffer`, `New-AircDccToken`, `Test-AircDccDoneSha256` (SelfTest covers them). Default TLS uses an **ephemeral** self-signed cert generated at runtime (cryptography; no private key in git). Override with `AIRC_DCC_TLS_CERT` / `AIRC_DCC_TLS_KEY`; lab-only plain with `tls=0`. Do **not** dump multi-KB base64 over PRIVMSG (Ergo fakelag will kill the console). Use `PUT` chunks / allowlisted HTTPS / a share for large files. The service paces PRIVMSG with a token bucket (`FLOOD_RATE_PER_S` / `FLOOD_BURST`); send failures force reconnect.

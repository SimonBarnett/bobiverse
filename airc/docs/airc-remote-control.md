# Airc remote control (protocol sketch)

See **[feature-request-airc-remote-control-2026-10-01.md](./feature-request-airc-remote-control-2026-10-01.md)** for LOCKED success metrics.

## Today (v0.1.x)

Authenticated PRIVMSG to `{machine}_console` runs PowerShell (or `cmd:` / `psb64:`) and returns Query lines `out`/`err`/`DONE id=??? exit=???`. The bob ear appends those to `<bob home>\airc-replies.jsonl` (FR #1546). `Invoke-AircRemote.ps1 -Outbox ??? -ReplyFile ???` prefixes `id=<corr>` and waits for matching DONE (non-zero exit on timeout).

**FR #4796 (driver pacing):** multi-line outbox bursts (`-Action Put` chunks) sleep `-OutboxPaceMs` (default 800, matches bob ear `FLOOD_S`) between lines. After a large reply (`>= -BurstReplyThreshold` out/err lines), `Invoke-AircRemote` sleeps `-PostBurstCoolMs` (default 2000) before returning so sequential Commands do not stack under Ergo fakelag. The bob ear also uses `CONSOLE_OUTBOX_FLOOD_S` (default 1.5s, env `BOB_CONSOLE_OUTBOX_FLOOD_S`) when draining `PRIVMSG *_console` from `home\outbox.txt`. Console reply token-bucket / truncate is FR #4790.

**FR #5539 / #5588 (over-long console PRIVMSG):** the bob ear never splits an over-long `PRIVMSG *_console` body (overflow would run as a second shell). It drops the wire send and writes synthetic `err id=<corr> seq=1 code=too_long bytes=N budget=B` plus `DONE id=<corr> exit=1` into `airc-replies.jsonl` / inbound-transcript so `Invoke-AircRemote` completes. Prefer a shorter command or DCC PUT for large payloads.

Concurrent Commands on the same Query are **queued** (FR #2632): one shell in flight plus a short pending list; each job still emits its own DONE. A full queue fail-closes with `busy: prior shell still emitting` + `DONE exit=1` (FR #2612: no hang). `Invoke-AircRemote` retries that busy reply within `-MaxRetries` / `-TimeoutSec` when `-JobId` was not pinned (compat with older airc).

On service stop / session interrupt, DONE for every in-flight and pending shell id is flushed **before** the IRC socket closes (FR #2640 / #2649) with **no per-line FLOOD_S delay** so SCM cannot kill the socket between err and DONE; `_stop_flushed` skips a second finally drain after sock=None. Late worker emits enqueue-only so stop never `sendall`s after close.

```text
PRIVMSG marchhare_console :id=aabbccdd Write-Output ping
PRIVMSG marchhare_console :id=aabbccdd cmd: echo %COMSPEC%
```

## Target verbs (FR)

| Verb | Purpose |
|------|---------|
| `STATUS` | Airc Running + VERSION files (bob/airc/jeeves); replies as `out id= seq=` then `DONE` (FR #2575) |
| `VERSION` | Current airc install version from `<ai root>\\airc\\VERSION` (missing -> `-`; no ARP fallback) plus `commit=` / `built=` from `BUILD.json` and `hotpatch=1` overlay from `HOTPATCH.json` (FR #5281 / #5534); same `out id= seq=` + `DONE exit=0` framing; allowed when `shell=off` / `jobs=off` like STATUS |
| plain line | PowerShell (default); UTF-8 `$OutputEncoding` wrap so StdOut keeps Greek/CJK (FR #2580); `$ProgressPreference=SilentlyContinue` so StdErr stays free of CLIXML progress noise (FR #2641); terminating / `Write-Error` StdErr is decoded from CLIXML to plain text with user-relative `At line:` (FR #2910 / #2918) |
| `cmd: ???` | COMSPEC escape hatch (`chcp 65001` prefixed, FR #2580); trailing `\` paths like `cmd: dir C:\` work (FR #3773: `/d /s /c` string cmdline, not list2cmdline) |
| `psb64:<b64>` | `powershell -EncodedCommand` (same UTF-8 wrap) |
| `PUT path` + chunks | Write file (base64 seq). Default `via=dcc` (FR #5194): send `DCCLISTEN` first; console dials out and reads `token\\n` + u32be + body + `sha256\\n`, verifies, writes via a temp file. `via=dcc` size cap is 2 MiB (`DCC_BULK_SIZE_CAP`, FR #5536); IRC PUT stays 256 KiB. On DCC fail the console stays in receiving and IRC `CHUNK`/`PUTEND` still land. `-ForceIrcPut` skips DCC. |
| `RUN path` | Execute; end with `DONE id=… exit=…` |
| `GET path` | hash/size + head (80 chars). Does not send the file. |
| `GET path fetch=chunk` then `GETCHUNK id seq` | FR #4795 outbound fetch. Open returns bytes/sha256/seqs only. Each GETCHUNK returns one <=300-byte raw chunk. The next GETCHUNK is the ack; the console never pushes the following chunk. |
| `UPDATE airc\|bob\|jeeves [ver]` | Allowlisted GitHub Release MSI via detached `Update-BobiverseService.ps1` (FR #77). Optional leading `id=<job>` (FR #5532). Reply is `UPDATE accepted id=...` then `DONE id= exit=`. Bare product (no ver) = **latest** release asset; optional `x.y.z` pin (FR #5280) |
| `PRIORITY prepare <ENAME>` | TYPE=P named prep: EXEC `REPPREPDIRECT2`; success only if SDK ok **and** `EXECPREPLOCK.UPD=N` **and** `.prp` mtime advanced (FR #5286). Never form-prep; never SQL-fake UPD; never a password on IRC |
| `PRIORITY connect|status [instance-id]` | Allowlisted Priority Web connect/status via CredMan; `out id=` JSON + `DONE id= exit=`; never password on IRC (FR #5284 / #5275). See [airc-priority-client.md](./airc-priority-client.md) |
| PRIORITY formStart|subform|getRows | FR #5285 read-path form walk via in-service fixture worker (JSON + DONE id= exit=). Allowlisted instance only; no passwords on IRC; no agent .mjs. |
| NETWORK / NETWORK diag [-WhatIf] | Isolated diagnostic worker (FR #5298 / docs FR #5301). UPDATE-class auth. Inventory hostname, ips[], ou. Full data+log via DCCLISTEN same job id or IRC CONT. |
| `LEGION {host|ip}` [-WhatIf] | Isolated in-service installer (FR #5308 / #5309 / docs FR #5312). UPDATE-class auth. CredMan `PriorityAirc/LegionAdmin`. Log via DCCLISTEN same job id or IRC CONT (FR #5311). |
| EXTENSION install|status [-WhatIf] | Isolated worker: DC + GPO Priority-web-extension ForceInstall Chrome+Edge then LDAP fill-holes (FR #5290/#5291/#5292). Fill-holes: machine account first, then CredMan `PriorityAirc/ExtensionAdmin` on access-denied (FR #5364; fail closed `credman-missing`; never on IRC). DCC/CONT log (FR #5293). Default id cgmpadejahkaggjpffnhaoiafbnicgpa. No DC -> GPO fail closed |

## UPDATE (FR #77 / FR #5280) - shipped

Authorized PRIVMSG only (operators list; `bob-<machine>` when seeded - FR #3286, never arbitrary `bob-*`):

```text
PRIVMSG marchhare_console :UPDATE airc
PRIVMSG marchhare_console :UPDATE airc 0.1.20
```

- **Bare `UPDATE airc` (no version)** = latest GitHub Release airc MSI for `SimonBarnett/bobiverse` (sha256-checked). The console schedules Check **without** `-TargetVersion`; `Update-BobiverseService.ps1` calls `GET /repos/.../releases/latest` and selects the matching `airc-x.y.z.msi` + `.sha256` (FR #5280 / parent Success S3). FR #5353: if `/releases/latest` 404s (prerelease-only / `--latest=false` catalog), Check lists `/releases` and picks the newest semver tag with the product MSI (non-prerelease preferred), with short retries on transient 403/429.
- **Pinned `UPDATE airc x.y.z`** = that release tag only (`-TargetVersion`; API `/releases/tags/vX.Y.Z`). Invalid/mismatched pins log `target-version-mismatch` and do not install.
- Schedules **Check** mode of `Update-BobiverseService.ps1` with `-ForceCheck` (and optional `-TargetVersion` only when pinned).
- Detached helper (scheduled task / WMI) runs **Apply** later; the live airc process never invokes `msiexec`.
- **FR #5277 restart:** Apply `finally` always `Ensure-ServiceRunning` so msiexec-timeout / download-failed / stop-failed / rollback still leave the service Running. Console reconnect budget **120s**. Matrix: [airc-update-restart-matrix.md](./airc-update-restart-matrix.md).
- Reply (`UPDATE accepted status=scheduled ...` or `UPDATE skipped-pending ...`) is sent **before** the transport is stopped.
- Assets must be `https://github.com/SimonBarnett/bobiverse/releases/download/...`; foreign URLs are rejected (`asset-url-rejected`). FR #5345: if GitHub omits `browser_download_url` or only returns `api.github.com/repos/.../releases/assets/<id>`, Check rebuilds the allowlisted download URL from tag + asset name (still rejects foreign hosts).
- Pending / loop-guard / rollback / sha256 mismatch behaviour is owned by the updater (same as service-start self-update).
- **FR #5279:** each distinct Apply/Check failure class (`download-failed`, `msiexec-exit`, `msiexec-timeout`, `stop-failed`, `backup-failed`, `spawn-failed`, `updater-missing`, `asset-url-rejected`, `stale-pending`, ???) files one `kind:issue` on `SimonBarnett/bobiverse` via intake. `idempotency_key` = `airc-update-fail|{machine}|{product}|{tag}|{result}` so retries do not twin-flood. Title/body are redacted. `Set-Failure` and `schedule_fleet_update` both call this path. Local `state.json` counts are unchanged. FR #5494: Check clears leftover pending when `pending.tag` is already at or behind installed VERSION (`pending-already-installed`) and does not file `stale-pending`.
- Machine id: explicit `-MachineId`, then `AIRC_CONSOLE_MACHINE` / `BOB_MACHINE_ID`; hostname fallback must be conscious (Start-AircConsole warns).


## PRIORITY connect/status (FR #5284 / #5275) --- shipped

Authorized PRIVMSG only (same operators / live +o/+h as other console verbs). Instance URLs come from the allowlist only; passwords from CredMan only.

```text
PRIVMSG marchhare_console :PRIORITY status
PRIVMSG marchhare_console :id=aabbccdd PRIORITY connect example-dev
```

- Allowlist: `<ai root>\\airc\\config\\priority-instances.json` (example: `airc/config/priority-instances.example.json`). Schema and CAST IRON rules: [airc-priority-client.md](./airc-priority-client.md).
- Replies: `out id=<corr> seq=1 <json>` then `DONE id=<corr> exit=0|1` (multi-line; console service splits on newlines).
- Live Web SDK worker packaging is FR-B (#5283); unit/SelfTest path may use a mock connector that never echoes the password.

## Encoding policy

- Short ops: **plain text** (readable in Halloy / irc.log).
- Scripts / `$` / spaces: **base64** (`psb64` or PUT).
- Secrets: **never** clear IRC ??? local files or agentic-file SEAL.
- Large logs/MSI: HTTPS allowlist or path drop ??? IRC is control plane.

## CAST IRON ops notes

- Prefer `UPDATE airc` over free-form `msiexec` / `Restart-Service Airc` mid-playbook ??? the transport dies if you kill airc yourself.
- LocalSystem ConsoleHome must not be `C:\Users\Default\.airc` (see post-install ??8b).
- Reserved nick + wrong GUID ??? oper `PASSWD {machine}_console <guid>` then restart Airc.

## Large replies / flood (FR #4790)

Shell replies are capped at `SHELL_REPLY_MAX_IRC_LINES` IRC `out`/`err` lines. Oversized output ends with `err ... output truncated, N lines omitted; CONT id=<job> (FR #4794); file fetch / PUT (FR #4790); DCCLISTEN (FR #5003)` then `DONE`. Send `CONT id=<job>` or `RESUME id=<job>` (optional `offset=N`) to fetch the next page without re-running the command.

**FR #5003 / #5008 bulk DCC:** for large listings, prefer a reverse TCP/TLS stream instead of IRC lines. Before (or with) the command, the caller may PRIVMSG:

`DCCLISTEN id=<job> host=<ip> port=<n> token=<hex> [tls=0|1] [relay=<host:port>]`

An optional leading job frame `id=<job> ` before `DCCLISTEN` is accepted (FR #5531); bare `DCCLISTEN` is unchanged. Without that strip, `id=... DCCLISTEN ...` is treated as PowerShell.

`tls=` defaults to **1** (FR #5008). When the shell output exceeds the bulk threshold and a matching listen offer exists, the console connects **out** to that host:port (or to `relay=` when both sides are NAT'd), sends `token\n` + `u32be length` + body + `sha256\n` (TLS-wrapped when `tls=1`), and replies on IRC with a short hint plus `DONE id=... exit=... bytes=N sha256=H via=dcc` (no body flood). If the handshake fails within a few seconds, it falls back to the IRC CONT path and emits `err ... dcc failed: ...; falling back to IRC` with the **next unused seq** immediately before `DONE` (FR #5065) ??? never `err seq=1` plus `out seq=1` (ConvertFrom-AircRemoteReply fail-closes on duplicate seq). Live MarchHare retest (FR #5069, tip `91648f9b`, job `b6782a52`): forced `DCCLISTEN` to closed port 1 yielded `err seq=50` then `DONE exit=0` with 50 unique seqs; `ConvertFrom-AircRemoteReply` parsed cleanly (evidence under `airc/docs/evidence/fr-5069-dcc-fallback-live-retest/`). `Invoke-AircRemote` helpers: `New-AircDccListenOffer`, `New-AircDccToken`, `Test-AircDccDoneSha256` (SelfTest covers them). Default TLS uses an **ephemeral** self-signed cert generated at runtime (cryptography; no private key in git). Override with `AIRC_DCC_TLS_CERT` / `AIRC_DCC_TLS_KEY`; lab-only plain with `tls=0`. Do **not** dump multi-KB base64 over PRIVMSG (Ergo fakelag will kill the console). Use `PUT` chunks / allowlisted HTTPS / a share for large files. The service paces PRIVMSG with a token bucket (`FLOOD_RATE_PER_S` / `FLOOD_BURST`); send failures force reconnect.

## EXTENSION (FR #5290 / #5293 / #5294) - shipped docs

Authorized PRIVMSG only (UPDATE-class: ops/half-ops; `update=off` refuses).

```text
PRIVMSG marchhare_console :id=aabbccdd DCCLISTEN id=aabbccdd host=127.0.0.1 port=7700 token=<hex> tls=1
PRIVMSG marchhare_console :id=aabbccdd EXTENSION install
PRIVMSG marchhare_console :id=aabbccdd EXTENSION install -WhatIf
```

- Default ForceInstall id: `cgmpadejahkaggjpffnhaoiafbnicgpa` plus `https://clients2.google.com/service/update2/crx` for Chrome and Edge.
- GPO happy path: `Priority-web-extension` at domain root (FR-B). Fill-holes: LDAP AD computers + remote registry (FR-C). Isolated worker (FR-A).
- Log: DCCLISTEN same job id (`DONE ... via=dcc` + sha256) or IRC CONT. CAST IRON: no passwords on IRC or in the DCC body.

## NETWORK (FR #5301) - docs contract

Authorized PRIVMSG only (UPDATE-class: ops/half-ops; `update=off` refuses). Isolated worker (FR-A #5298). Inventory fields (FR-B #5299): `hostname`, `ips[]`, `ou`.

```text
PRIVMSG marchhare_console :id=aabbccdd DCCLISTEN id=aabbccdd host=127.0.0.1 port=7700 token=<hex> tls=1
PRIVMSG marchhare_console :id=aabbccdd NETWORK diag
PRIVMSG marchhare_console :id=aabbccdd NETWORK diag -WhatIf
```

- Same job `id=` on DCCLISTEN and NETWORK. Success: short IRC accepted + `DONE ... via=dcc` (or CONT). CAST IRON: no secrets on IRC or in the DCC body.
- `shell=off` / not-op use the existing `DONE exit=126` exits. Worker fault must not stop Airc.

## LEGION (FR #5312) - docs contract

Authorized PRIVMSG only (UPDATE-class: ops/half-ops; `update=off` refuses). Isolated worker imports `airc_network_installer` (FR #3991). One hostname or IPv4.

```text
PRIVMSG marchhare_console :id=aabbccdd DCCLISTEN id=aabbccdd host=127.0.0.1 port=7700 token=<hex> tls=1
PRIVMSG marchhare_console :id=aabbccdd LEGION walrus
PRIVMSG marchhare_console :id=aabbccdd LEGION walrus -WhatIf
```

- CredMan `PriorityAirc/LegionAdmin` via secure env. CAST IRON: no secrets on IRC or in the DCC body.
- Same job `id=` on DCCLISTEN and LEGION. WhatIf is dry-run (no remote install).
- FR #5530: -WhatIf still probes MSI/PsExec when CredMan is missing; the DCC log includes msi, psexec, summary=dry-run, and a credman-missing failure row (live installs still fail closed before install_remote).

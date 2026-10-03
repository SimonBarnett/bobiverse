<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/airc-console-fr253.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #253 — airc console service

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/253

## Goal

Installable **airc** service on each Windows box:

1. If **`#{machinename}`** is ChanServ-registered: JOIN as **`{machinename}_console`**
2. Else lobby on **`#{domain_or_workgroup}`** as **`{machinename}`** (433 → `_1`, `_2`, …) for that session
3. Register / identify the nick (reuse `console.password` GUID)
4. Stay **silent** in the chosen channel
5. Per authenticated user: PRIVMSG session → interactive console pipe
6. Only authenticated users may PRIVMSG the console
7. Ship as a **single release MSI** (+ checksum) — issue #305

See also `docs/airc-console-domain-lobby.md`.

## Acceptance (MVP)

| Gate | Proof |
|------|--------|
| Channel naming | `shop_channel("IONOS") == "#ionos"` |
| Silent channel | Public PRIVMSG on `#{machine}` never answered on-channel |
| Auth gate | Unknown nick → deny reply in Query; operator → pipe |
| Session | Per-nick shell; `.quit` closes |
| Service install | `Install-AircConsole.ps1` registers NSSM `AircConsole` |
| Unsigned download install (FR #256) | `Install-AircConsole.cmd` uses Unblock-File + `-ExecutionPolicy Bypass` |
| UAC self-elevate (issue #305) | `Install-AircConsole.ps1` requests UAC via `Start-Process -Verb RunAs` when not already admin (no `#Requires -RunAsAdministrator`) |
| Single MSI release (issue #305) | `Pack-AircConsoleRelease.ps1` builds `dist/airc-console-*.msi`; GitHub release attaches MSI only |
| Start on mapped drive / CmdletBinding (FR #259) | `Start-AircConsole.ps1` resolves script dir in body — never `$PSScriptRoot` in `param()` defaults |
| Bundled NSSM (issue #266) | Release MSI includes `third_party/nssm/win64/nssm.exe`; install does **not** require `C:\ai\ergo\nssm.exe` |
| NickServ GUID (issue #271) | First start mints GUID into `console.password`; reuse next start; Ergo PASS stays separate |
| Reinstall (issue #273) | `Install-AircConsole` stops+removes any existing `AircConsole` then installs fresh; nssm "not been started" stderr is ignored |
| Unattended (issue #277/#294) | Seeds `ergo.password` from **release** `config/ergo.password` (not target `~\.grok`), mints NickServ GUID, **Start-Service** → Running |
| LocalSystem Python (issue #282) | Install bakes absolute `python.exe` into NSSM `-Python`; Start resolves when PATH empty |
| Unique nick / domain lobby | ChanServ INFO `#{machine}` → `{machine}_console` on shop, else `#{domain}` as `{machine}`/`_{n}`; see domain-lobby FR |
| Reconnect + ping (issue #298) | Auto-reconnect on EOF/ERROR/dead socket; answer CTCP PING and `ping flam*` |
| Fleet bob-* (issue #302) | Any `bob-{machinename}` nick may drive the console (already Ergo-auth'd) |
| Release | `Pack-AircConsoleRelease.ps1` builds `dist/airc-console-*.msi` |
| Selftest | `airc_console_service.py --selftest` exit 0 |

## Install notes (FR #259 / #266 / #305)

Preferred client path: download **`airc-console-<ver>.msi`** and run it (per-machine UAC).
The MSI lays down `C:\ai\airc-console` and runs `Install-AircConsole.cmd` elevated.

**Issue #309:** `airc-console-v0.1.16` MSI exits 1603 (`CAQuietExec64` failed to get
command line data) because deferred quiet-exec used `QtExecCmdLine` instead of
`CustomActionData` (`Property="RunAircInstall"` in `packaging/airc-console/Product.wxs`).
Workaround until a patched MSI: `msiexec /a … /qn TARGETDIR=…` then copy to
`C:\ai\airc-console` and run `scripts\Install-AircConsole.cmd`.

From an unpacked tree / `.cmd`: `Install-AircConsole.ps1` **self-elevates** (UAC) when
the caller is not already an administrator (issue #305).

NSSM **Application** must be `powershell.exe` (not the `.ps1`). Prefer a **local** install tree (`C:\ai\airc-console\scripts\…`) over a mapped download drive (`P:\download\…`). Mapped drives + `[CmdletBinding()]` left `$PSScriptRoot` empty in param defaults and crashed `Start-AircConsole.ps1` before Python ran.

**NSSM binary:** the release MSI ships `third_party/nssm/win64/nssm.exe` (public domain, https://nssm.cc). `Install-AircConsole.ps1` resolves that path first, then legacy `C:\ai\ergo\nssm.exe`, then `PATH`. Pass `-Nssm` only to override.

Do not name a PowerShell parameter `$Home` (automatic read-only) — launchers use `-ConsoleHome`.

Ergo (`irc.ntsa.uk`) needs a server **`PASS`** before `NICK`/`USER`. That secret
is **packed into the release MSI** as `config/ergo.password` (issue #294) and
copied by Install into `~\.airc-console\ergo.password`. Target clients do **not**
need `~\.grok`. Never invent the secret.

**NickServ** (issue #271): on first start the client **mints a GUID** into
`~\.airc-console\console.password` and reuses it for REGISTER/IDENTIFY. Operators
do not choose this password. SASL (optional `--sasl`) uses the same GUID.

## Non-goals (this PR)

- Not a fleet talk seat / digester / Mode 3 PIN chair
- No `#bobiverse` presence
- No claim of live human UAT on every box from CI

## Layout

- `scripts/airc_console.py` — offline core
- `scripts/airc_console_service.py` — TLS IRC host
- `scripts/Start-AircConsole.ps1` / `Install-AircConsole.ps1` / `Pack-AircConsoleRelease.ps1`
- `src/airc_console/` — VERSION + README for release staging
- `.grok/skills/airc-console/SKILL.md`
- `tests/test_airc_console_fr253.py`

## Auth

Operators file / CLI nick allowlist. Optional services **account** allowlist via IRCv3 `account-tag` / `AccountMap` (FR #230). Empty operators **and** accounts → refuse start.

# FR: airc PowerShell remote + job/PUT protocol

Target: `SimonBarnett/bobiverse` (airc product). Extends existing `{machine}_console` PRIVMSG shell.
Session evidence: DigSTAT / MSI fleet cutover 2026-09-30 (marchhare/win-mpre gist roulette, cmd quoting, 400-char clip, airc self-kill).

## Objective

Make authenticated airc remote control usable for agents: PowerShell-first shell, hybrid cleartext/base64 jobs, structured DONE/exit, and safe fleet update verbs — without replacing Ergo or inventing interactive UAC over IRC.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Default shell is PowerShell | New console session runs PowerShell 5.1 (cmd via `cmd:` only) | PRIVMSG `echo $PSVersionTable.PSVersion` returns a Version; `cmd: echo %COMSPEC%` still works | Default session is cmd.exe / `$PSVersionTable` fails |
| S2 | EncodedCommand path | `psb64:<base64>` runs without IRC `$`/quote mangling | Round-trip script with `$env:COMPUTERNAME` exits 0 and prints host | Encoded line refused or mangled |
| S3 | Deploy script without public gist | `PUT` + chunks + `RUN` (or allowlisted HTTPS pull) yields `DONE id=… exit=0` | irc.log / Query shows DONE with exit code for a 50-line `.ps1` | Agent must publish a public gist to run multi-line work |
| S4 | STATUS one round-trip | `STATUS` returns Airc Running + bob/airc/jeeves VERSION when present | Single PRIVMSG reply block (or sequenced NOTICEs) parseable by agent | Must scrape `type C:\ai\*\VERSION` across many lines |
| S5 | Airc self-update does not strand nick | `UPDATE airc` defers recycle or restarts after disconnect; console rejoins within 120s | After UPDATE, `{machine}_console` answers `echo ping` within 120s | Nick stays `401 No such nick` after airc MSI via airc |

LOCKED

## Shape

Primary (one): service

Hybrid note: protocol is IRC PRIVMSG to existing Windows service `Airc`; optional controller helper script on the driving box. No customer website / no new GUI.

LOCKED

## Stack

Default: keep Python `airc_console` / `airc_console_service` IRC core; change piped user shell to PowerShell; base64 chunk framing on IRC; allowlisted HTTPS for large pulls; SEAL/agentic-file only for secrets.

Why: Matches live fleet and approved plan (IRC control plane, not SSH/WinRM replacement).

Why-not: Full ConPTY streaming or interactive UAC over IRC — out of scope.

LOCKED

## Architecture

```
bob-{mid} / operator
  PRIVMSG {mid}_console :STATUS|psb64:…|PUT|RUN|UPDATE|cmd:…
       │
       ▼
Airc (python IRC) ──auth──► per-user shell session
       │                      default: powershell -NoProfile
       │                      opt: cmd:  /  psb64: EncodedCommand
       ▼
Query PRIVMSG/NOTICE back: output lines + DONE id= exit=
Large files: PUT chunks or HTTPS allowlist (GitHub Releases)
Secrets: never clear IRC (SEAL / local files)
UPDATE airc: download MSI → start /wait → schedule reconnect (do not strand transport)
```

LOCKED

## Screens

No new UI. Reuse bobiverse vision mocks as protocol placeholders (validator gate).

| id | file | state |
|----|------|-------|
| M1 | docs/mocks/home.html | primary |
| M2 | docs/mocks/empty.html | empty |
| M3 | docs/mocks/error.html | error |

## Gap vs current tree

| Area | Today | FR |
|------|-------|-----|
| Shell | `DEFAULT_SHELL = COMSPEC` (cmd.exe) | PowerShell default; `cmd:` escape |
| Encoding | Plain lines only | Plain short + `psb64:` + PUT chunks |
| Output | `line[:400]` silent truncate | Paging / DONE framing |
| Jobs | None (gist + irm) | PUT/RUN/JOB/STATUS |
| Self-update | Free-form msiexec kills console | UPDATE verb + defer |

## Phases

1. **FR-A** Shell ergonomics (PS default, psb64, exit trailer)
2. **FR-B** Job/file protocol (PUT/RUN/GET/JOB/STATUS + DONE)
3. **FR-C** Fleet UPDATE verbs + airc self-update safety
4. **FR-D** `Invoke-AircRemote.ps1` controller helper + skill docs

## Non-goals

- Replace Ergo with SSH/WinRM
- Interactive UAC from IRC
- Full PTY/ConPTY streaming (later)

## LOCKED decisions

- Default shell: PowerShell 5.1
- Encoding: plain short; base64 for PUT/EncodedCommand; SEAL for secrets
- Large files: HTTPS allowlist + PUT chunks
- Implementation home: bobiverse `airc` first (not agentic_irc fork)
- Park docs/issue first; no MSI bump until implementation PR

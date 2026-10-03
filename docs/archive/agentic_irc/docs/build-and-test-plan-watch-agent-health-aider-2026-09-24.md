<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-watch-agent-health-aider-2026-09-24.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: Watch-AgentHealth -Aider live REPL wake (2026-09-24)

**Date:** 2026-09-24 (Europe/London)  
**Repo:** SimonBarnett/agentic_irc  
**Branch:** `feature/watch-agent-health-aider`

## Problem

MarchHare talk seat `marchhare-11820` uses IrcHome `~\.agentic-irc-aider`.
`Start-TalkSeat` starts `irc_agent` + `irc_listen` only — no watcher.
`listen.stdout.log` already receives `FROM` (e.g. `FROM simon #marchhare ping`),
but live `aider.exe` REPL is never woken. Cursor cloud agents are exhausted;
Grok/Cursor Watch-AgentHealth modes spawn CLI one-shots, which is wrong for Aider.

## Goals

1. Add `-Aider` / `--aider` to `scripts/Watch-AgentHealth.ps1` (mutually exclusive with `-Grok` / `-Cursor`).
2. Default IrcHome for Aider: `%USERPROFILE%\.agentic-irc-aider`.
3. Poll listen sinks the same way as Grok/Cursor (`agent_health.py` select-sink / read-from).
4. On new `FROM` lines, inject the wake text into the **existing** `aider.exe` console
   (SendKeys on parent PowerShell HWND; child-process `AttachConsole` + `WriteConsoleInput` if no HWND).
   **Never** `aider --message` one-shot.
5. Optional `-AiderPid` when multiple aider processes exist.
6. Offline pytest updates; brief starter doc. No UAT stamp. Draft PR only.

## Non-goals

- Changing `Start-TalkSeat` to auto-start the watcher (call out in starter note).
- agentic_build `setup-bob-aider` install skill changes (follow-up note only).
- Merging to main / live recycle from this PR worker.

## Interim start (after Start-TalkSeat for aider home)

```powershell
# Seat already up: nick=marchhare-11820 home=%USERPROFILE%\.agentic-irc-aider
# Live REPL e.g. aider.exe pid 38640 in parent PowerShell console.
powershell -NoProfile -ExecutionPolicy Bypass -File D:\ai\agentic_irc\scripts\Watch-AgentHealth.ps1 `
  -Aider -IrcHome "$env:USERPROFILE\.agentic-irc-aider" -AiderPid 38640 `
  -Scripts D:\ai\agentic_irc\scripts -Cwd D:\ai\agentic_irc
```

Or Haitch-style: copy `Watch-AgentHealth.ps1` from this branch into `%TEMP%\haitch-watch-agent-health.ps1`
and/or the seat home, then run with `-Aider`.

## Honesty-box / harvest

Learned 2026-09-24 on MarchHare: `aider.exe` often has `MainWindowHandle=0`; the
visible console HWND belongs to the parent `powershell -NoExit` that launched
`Start-AiderRepl.ps1`. Prefer SendKeys on that parent HWND; use a short-lived child
for `AttachConsole`/`WriteConsoleInput` so the watcher does not `FreeConsole` itself.
Skill book: harvest into `setup-bob-aider` (agentic_build) when that skill is next
edited — note only here.

## Follow-up

- agentic_build `setup-bob-aider`: document watcher one-liner after REPL start.
- Tray / AgentMonitor: optional Aider watch shortcut (out of scope for this PR).

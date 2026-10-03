<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/watch-agent-health-aider.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Watch-AgentHealth -Aider (live REPL)

After `Start-TalkSeat.ps1 -MachineId marchhare -IrcHome $env:USERPROFILE\.agentic-irc-aider`
(starts `irc_agent` + `irc_listen` only), start a **visible** `aider.exe` REPL in its
own PowerShell window, then start the watcher:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Watch-AgentHealth.ps1 `
  -Aider -IrcHome "$env:USERPROFILE\.agentic-irc-aider" `
  -Scripts (Resolve-Path .\scripts) -Cwd (Resolve-Path .)
```

Optional: `-AiderPid <pid>` when more than one `aider.exe` is running.

The watcher polls `FROM` lines and types the wake into the live REPL
(SendKeys on parent console HWND; WriteConsoleInput child fallback). It does **not** call `aider --message`.

Grok/Cursor modes are unchanged (`-Grok` / `-Cursor`).

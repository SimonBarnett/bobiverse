<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-document-agentmonitor-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: Document AgentMonitor (issue #1)

**Ask (Simon `#bobiverse` 2026-09-23):**
https://github.com/SimonBarnett/AgentMonitor needs documenting please.

## Summary

The repo has a working monitor (`Watch-AgentHealth.ps1` + `.cmd` launchers)
and a short README. Operators and agents need a real document: what it
starts, what it does not touch, how IRC is forwarded, how resume works,
and how to launch it on a Restricted ExecutionPolicy box.

## Gap vs main (`1a09848`)

`README.md` is a launch cheat-sheet. Comment header on the `.ps1` has the
contract, but it is not operator docs. No `/docs` playbook. No issue.

## LOCKED (from the current script + Simon 2026-09-22/#bobiverse)

1. Switch is `--grok` (`agent.exe`) or `--cursor` (`agent.cmd`).
2. Persist session id so Resume does not reload all skills. `new` starts
   a fresh session.
3. Agent still initialises IRC. The monitor does not start, stop, or
   health-check `irc_listen`.
4. Monitor tails `$IrcHome/irc.log` and resume-forwards each PRIVMSG as
   a `FROM` line into the agent session. Agent TSR is data, not a second
   listener.
5. Own IRC home only: `~\.agentic-irc-watch-grok` / `~\.agentic-irc-watch-cursor`.
   Do not touch `~\.agentic-irc-cursor`, `~\.agentic-irc-cursor-2`, or the
   bobiverse Watch home.
6. Direct `.ps1` fails when ExecutionPolicy is Restricted. Launch via
   `.cmd` (`-ExecutionPolicy Bypass`) or the shortcuts.
7. Workspace is `\ai` on a D:..Z: drive (create if missing). Do not
   default C:\ unless the operator passed `-Cwd`.
8. Does not stamp UAT. Does not send `!bobiverse`.
9. Hidden `-WatchWorker` monitor. Opens the Cursor Composer / grok TUI
   (no extra PowerShell TUI launcher).

## UNKNOWN

- Exact shortcut icon paths on each machine's Desktop (not in this repo's
  empty `shortcuts/` tree).
- Whether Desktop copies on flamingo / marchhare / ionos match this SHA.

## Acceptance

- A1: `docs/` has an operator document (how to launch, resume vs new,
  homes, log path, what is forbidden).
- A2: `README.md` points at that document and keeps the launch cheat-sheet.
- A3: LOCKED vs UNKNOWN marked. No invented URLs, tokens, or nicks.
- A4: No UAT stamp.

Workers do not stamp UAT.


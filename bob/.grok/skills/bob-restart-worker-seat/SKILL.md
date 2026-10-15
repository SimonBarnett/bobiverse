---
name: Bob restart worker seat
description: >-
  Use when a Bob Fleet watch seat (Grok/Cursor worker) looks hung, stops ACKing,
  needs a fresh session, is out of tokens, or a second seat on one machine
  misbehaves.
---
# Bob restart worker seat

Home skill book: https://github.com/SimonBarnett/agentic_build (honesty box: report gaps there). Three Laws: follow skill-tree CAST IRON.

## 1. Diagnose before touching anything (read-only)
- Map the seat from its `state.json` (`ircHome`, `clientSlot`, `rootPid`, nick) and the process tree: monitor (`Watch-AgentHealth.ps1 -WatchWorker`), agent root, `agent -p` runs, irc_agent and irc_listen. Never trust PIDs from memory; they change after hotpatches.
- **Slow is not the same as hung.** Check the agent's own log for the prompt size and time to first token before calling a run hung. A resumed oversized session (for example a 12–22 MB `updates.jsonl`, about 380K prompt tokens) can take over 7 minutes to produce its first token while still at under 1s CPU.
- **Out of tokens is not the same as hung.** Look for 402/429, "usage balance exhausted" or `creditUsagePercent: 100`. Check the tray log for `fuel remaining 0` and `sessionKey=yes`. A seat started with a session key runs on that key only.
- **Two seats, one nick:** if a second seat logs "irc seat already up nick=<seat1 nick>", it has bound to slot 1's IRC home (a known monitor bug). Both seats will then run the same ASSIGN.

## 2. Rules
- Ask before stopping or restarting a seat, unless the user has already approved that exact action.
- **No tokens left on the machine:** never start a seat automatically, and never start one without a key. Start it only through the tray's out-of-tokens path, so the API key dialog appears on the machine's desktop and the user types the key. If there's no external trigger for that path, tell the user which tray menu item to click. If the user says they'll do it, do nothing.
- Never close a mis-bound second seat from the tray. Its teardown would disconnect seat 1. Force-stop its own PIDs only.
- Never touch the bob-{machine} ear, the tray, the job watcher, Ergo or Jeeves.
- Don't start a second seat on a machine while the slot-binding bug is open.

## 3. Fresh-session restart (when approved and tokens or a key are available)
1. Record the seat's exact launch command (the tray uses `-WindowStyle Hidden -File <Desktop>\Watch-AgentHealth\Watch-AgentHealth.ps1 -WatchWorker -Grok -New`).
2. `Stop-Process -Force` the seat tree by PID only: hung runs, then the agent root, irc_agent, irc_listen and the monitor. Confirm the nick QUIT and the ear is still alive.
3. Move the old session folder into `_archive-<date>-hung` (never delete it), along with copies of the logs and state.
4. Start ONE seat in the user's interactive session: use the tray path, or a one-shot interactive scheduled task as the logged-on user that you delete once it has fired. `-New` always, never a resume.
5. Verify: a new session ID, a nick `{machine}-{monitorpid}` JOINed to `#{machine}` only, slot 1, and a startup turn that completed with CPU progress. Try at most 2 starts, then capture evidence and report.
6. Re-send any ACKed-but-not-DONE job marked "retry, prior ACK void". Never re-send while an ACK is open on a live run.

## 4. Harvest
File the gaps you find as issues in the home repo (monitor bugs in AgentMonitor, tray/start in agentic_build). Workers write the fixes.

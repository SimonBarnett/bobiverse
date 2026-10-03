<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-restart-worker-seat/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-restart-worker-seat
description: >
  Diagnose and restart a hung or misbehaving watch/talk seat. Distinguish
  slow first-token from hung, out-of-tokens from hung, and mis-bound slot 2
  from a real seat-1 hang. Use when the user says restart the seat, hung
  seat, slow seat, out of tokens seat, slot 2 same nick, fresh session
  restart, or /bob-restart-worker-seat. Named Grok Bot Temporal hangs are
  unstick-grok-bot. Ear/tray recycle is bob-fleet-tray / killproc for talk
  seats. Never touch Ergo or Jeeves.
---

# Restart worker seat (diagnose first)

Foundation: harvest-agent-skills (honesty box) -> report back to
https://github.com/SimonBarnett/agentic_build.

Harvested from Bob-1 (2026-09-25): flamingo seat stopped as "hung" while it
was still working on a huge resumed session (first token ~445s, CPU idle).
Related automated fixes: AgentMonitor #97 (slot binding), agentic_build
#99/#101 (hang detection), #345 (second seat IrcHome), #346 (Restart
watcher reinstall), #352 (busy seats / restart policy).

## CAST IRON

1. **Diagnose read-only first.** Map the seat from `state.json` + process
   tree for **this** home. Never from remembered PIDs.
2. **Ask the user** before stopping or restarting a seat.
3. **Never touch** the ear (`bob-*`), the tray, the job watcher, Ergo, or
   Jeeves unless Simon named that target.
4. **Mis-bound seat 2:** if tray log says `irc seat already up nick=<seat1>`,
   slot 2 is on seat 1's home (AgentMonitor #97 / #345). Do **not** stop seat 2
   via tray teardown (it disconnects seat 1). Force-stop only seat 2's own PIDs.
5. **Out of tokens:** do not auto-start. Use the tray out-of-tokens path so
   the session key dialog appears. If the user will start it, do nothing.
6. **Fresh-session restart:** archive the session (never delete); start ONE
   `-New` seat; verify nick `{machine}-{pid}` on `#{machine}` only; at most
   two start attempts; re-send ACKed-but-not-DONE jobs as retry (prior ACK void).

```mermaid
flowchart TD
  A[Read state.json + process tree] --> B{Classify}
  B -->|log shows long TTFT / huge prompt| C[Slow — wait or archive+New]
  B -->|no progress + no CPU + no log| D[Hung — ask user then restart]
  B -->|402 / fuel 0 / sessionKey| E[Out of tokens — tray key dialog only]
  B -->|slot2 nick equals seat1| F[Mis-bound — kill seat2 PIDs only]
  C --> G[Ask user before stop]
  D --> G
  E --> H[Do not auto-start]
  F --> I[Never tray-stop slot2]
  G --> J[Archive session _archive-date-hung]
  J --> K[Start ONE -New interactive]
  K --> L[Verify nick machine-pid on #machine]
```

_Caption: diagnose (slow / hung / no tokens / mis-bound), then ask before restart; archive never delete; one `-New` start._

## Diagnose checklist

| Signal | Meaning | Action |
|--------|---------|--------|
| Huge `updates.jsonl` / prompt tokens; long time-to-first-token; low CPU | **Slow**, not hung | Prefer wait; or archive + fresh `-New` with user OK |
| No log progress, no CPU, no ACK after long idle | Likely **hung** | Ask user; then fresh-session restart |
| Tray `fuel remaining 0`, `sessionKey=yes`, 402 / usage exhausted | **Out of tokens** | Tray key-dialog path only; never silent start |
| `irc seat already up nick=<other>` on slot 2 start | **Mis-bound** home | Kill only slot-2 PIDs; fix via #97/#345 deploy |

## Fresh-session restart (after user OK)

1. Record the launch command / slot / IrcHome from state.
2. Stop the seat tree by **those PIDs only** (not tray Stop that tears down IRC for another slot).
3. Archive the session dir to `_archive-<yyyyMMdd>-hung` (never delete).
4. Start **one** `-New` watch/talk seat via tray path or a one-shot interactive
   scheduled task (delete the task after it fires). Prefer interactive session
   so the TUI is visible.
5. Verify: nick = `{machine}-{rootPid}`, JOINed `#{machine}` only, slot 1 unless
   intentional slot 2 with its own home, first turn completed.
6. At most **two** start attempts.
7. Re-queue ACKed-but-not-DONE work: tell the seat "retry, prior ACK void".

## Do not

- Close mis-bound seat 2 from the tray Agents stop (disconnects seat 1).
- Auto-start when the box has no tokens / no key.
- Touch ear, tray process (except asking user to use Restart watcher #346),
  Watch-BobJobs, Ergo, or Jeeves.
- Invent PIDs or kill another home's IRC children.

## Related

| Concern | Skill / issue |
|---------|----------------|
| Talk-seat kill/roll | `killproc` |
| Named Grok Bot Temporal | `unstick-grok-bot` |
| Tray Restart watcher full reinstall | `bob-fleet-tray` / #346 |
| Second seat explicit IrcHome | #345 / AgentMonitor #97 |
| Hang / wake queue | #99 / #101 |
| Busy seats during reinstall | #352 |

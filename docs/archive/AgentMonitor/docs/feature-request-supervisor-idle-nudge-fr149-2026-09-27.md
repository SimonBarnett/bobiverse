<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-supervisor-idle-nudge-fr149-2026-09-27.md, last changed 2026-09-27. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #149: AgentMonitor owns local worker supervision

## Objective

AgentMonitor on the worker box owns process health, idle detection, IRC
nudges, automatic restart of hung seats, and rich digest `working_on`
updates. Jeeves only consumes webhooks / updates the board — no remote
process control.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Idle nudges | PRIVMSG to seat nick at 20 / 40 / 60 min idle; max 3; never ping Simon on nudge | unit plan + outbox assert | Channel ping to Simon; >3 nudges |
| S2 | Restart after 3 failed nudges | Kill hung root + Start-WatchedAgent once; one retry; then PM simon | unit plan + source contract | Restart on first idle; FR #126 root-exit path broken |
| S3 | Board idle on DONE | Digest `working_on` = `currently idle` after DONE | helper unit test | Repo name left after DONE |
| S4 | Rich accept description | `working_on` includes worker type, pid, irc nick, model, task, friendly repo | helper unit test | Missing fields / raw URL only |
| S5 | Token-less | No LLM on nudge/restart/webhook path | scripts only | Model call in supervisor |

## Locked (Simon / issue #149)

- Escalation after **two** failed restarts: **IRC private message to `simon`** (not channel).
- Boot: existing Watch-AgentHealth launch already starts the agent; this FR adds **hung-idle restart**, not a new boot service.
- Dead TUI / root exit stays **FR #126** (teardown + monitor exit). Supervisor restart applies when the root is **still alive** but idle through three failed nudges.
- Webhook schema (draft below) is emitted by AgentMonitor; Jeeves board rendering may follow in a sister FR.

## Webhook draft (`POST /bob/v1/report` merge)

```json
{
  "op": "merge",
  "machine": "ionos",
  "working_on": "currently idle",
  "watch_job": {
    "worker_type": "grok",
    "pid": 10908,
    "irc_nick": "ionos-14020",
    "model": "grok-4.5",
    "task": "FR",
    "repo_friendly": "gh-Jeeves",
    "repo": "SimonBarnett/gh-Jeeves",
    "issue": 187,
    "state": "idle"
  }
}
```

Busy example `working_on`: `grok pid=10908 nick=ionos-14020 model=grok-4.5 FR gh-Jeeves`.

## Non-goals

- Jeeves remote kill/restart.
- Changing FR #126 root-exit teardown.
- design-uat / vision-UAT product semantics (gh-Jeeves FR #187).

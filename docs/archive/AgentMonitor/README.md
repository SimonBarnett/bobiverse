<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path README.md, last changed 2026-09-27. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# AgentMonitor

Desktop monitor that starts a Grok or Cursor **watch-seat** agent, watches the process, and forwards IRC `FROM` lines into that session. The agent still connects to IRC per `agentic-irc`; the monitor tails `irc.log` only.

**Operator documentation:** [docs/operator-playbook.md](docs/operator-playbook.md) (launch, resume vs `new`, IRC homes, Restricted ExecutionPolicy, LOCKED vs UNKNOWN).

**Feature request:** [Issue #1](https://github.com/SimonBarnett/AgentMonitor/issues/1). **MRB:** [Issue #3](https://github.com/SimonBarnett/AgentMonitor/issues/3). This repo does not stamp ready for human UAT.

## Launch

From a copy of this repo (or your deployed `Watch-AgentHealth` folder), double-click a shortcut if you have one, or run:

```bat
Watch-AgentHealth.cmd grok
Watch-AgentHealth.cmd grok new
Watch-AgentHealth.cmd cursor
Watch-AgentHealth.cmd cursor resume
Watch-AgentHealth.cmd grok off
Watch-AgentHealth.cmd cursor new off
```

- **Default / `new`** — fresh session id + full skills + seed prompt (CAST IRON for all Desktop links and tray Agents clicks).
- **`resume`** — rare recovery only; reuses the stored session id. Desktop / tray links never use this.
- Visible by default (watch console + agent TUI). **No `on` flag.**
- **`off`** — neither window; monitor log still receives lines. One-shot `agent -p` forwards stay hidden.
- **`new` / `resume` and `off`** may appear in either order on the main `.cmd`.

One-click `.cmd` files and Desktop shortcuts start in the background (`-Windows off`) and **always** pass `-New`. Legacy `*Resume*` shortcut names still launch a new session. Refresh Desktop icons with `tools\Publish-DesktopShortcuts.ps1` (IconLocation = agent `.exe`). Repo `shortcuts/*.lnk` are generated per machine and gitignored, so publishing never dirties the clone.

**Skills:** `.grok/skills/agent-monitor` and `.grok/skills/watch-seat` (also under `.cursor/skills/`).

On **Restricted** ExecutionPolicy, use these `.cmd` wrappers (`-ExecutionPolicy Bypass`). Do not rely on `.\Watch-AgentHealth.ps1` alone.

## IRC homes (watch seat only)

- Grok seat 1: `%USERPROFILE%\.agentic-irc-watch-grok`
- Grok seat N≥2: `%USERPROFILE%\.agentic-irc-watch-grok-N` (e.g. `-2`)
- Cursor seat 1: `%USERPROFILE%\.agentic-irc-watch-cursor`
- Cursor seat N≥2: `%USERPROFILE%\.agentic-irc-watch-cursor-N`

Each seat binds its own home, nick `{machine}-{pid}`, state dir, and log (**FR #97**). Seat N never adopts seat 1's `irc_agent`/`irc_listen`, never truncates another seat's log, and never QUITs another seat on stop.

Do not use talk-seat / bobiverse Watch homes (see playbook).

**Channels:** each watch seat JOINs its own `#{machine}` only (never `#bobiverse` / `#agentic_irc`).

**`!bored` (FR #100):** the monitor posts `PRIVMSG #{machine} :!bored` on seat start, right after the seat's `DONE`, and every few minutes while idle — never while busy (open ACK or pending `agent -p`). No LLM turn. Jeeves assigns the next job; the seat ACKs.

**Idle supervisor (FR #149):** while a fleet seat stays idle, the monitor PRIVMSG-nudges the **seat nick** at 20 / 40 / 60 minutes (max three; never pings Simon on nudge). After three failed nudges it kills the hung-alive agent tree and starts a fresh instance of the same kind (one restart retry). Two failed restarts → IRC **PM to `simon`**. Digest `working_on` becomes `currently idle` on DONE and a rich one-line description on ACK (worker type, pid, nick, model, task, friendly repo). Dead TUI / root exit remains **FR #126** (monitor teardown — no orphan `!bored`). Loop seats: `-NoIdleSupervisor` (implied by `-SeatType loop`).

**Loop seat (FR #103):** continuous non-job agents (e.g. ce-dayworks) use `-SeatType loop -Channel '#ce-priority-dev1' -Nick dayworks-dev1` (or `-NoBored`). That suppresses every `!bored` and the fleet ACK/DONE brief. Nick must **not** be `{machine}-{pid}` so Jeeves never assigns.

**Forward dedupe (FR #105):** identical IRC `FROM` lines are skipped for `-ForwardDedupeSeconds` (default **60**), then forwarded again. Every skip is logged (`forward skipped (duplicate within …)`).

**Wake lifecycle (FR #91):** at most one hidden `-p` wake per session. Further FROM lines queue
(coalesce duplicates). `-WakeTimeoutSeconds` (default **1800**) kills hung wakes (`wake timeout`).
On monitor start, orphan `-p` wakes whose parent is dead are reaped; interactive TUI (no `-p`) is never touched.

**Visible IRC wakes (FR #90 Option B):** each hidden `agent -p` / Cursor `-p` forward is logged to
`%USERPROFILE%\.grok\agent-health\watch-<kind>-<slot>\seat-wake-transcript.log` with
`wake start … pid=` and later `wake end … exit=`. With `-Windows on`, the monitor opens a
**Watch seat IRC wake transcript** console that tails that file so the seat does not look idle
while work runs off-screen. The Composer/Grok TUI still does not reload those turns in-place
(no keystroke injection).

## Log (not in git)

- Seat 1: `%USERPROFILE%\Desktop\Watch-AgentHealth\Watch-AgentHealth.log`
- Seat N: `%USERPROFILE%\Desktop\Watch-AgentHealth\Watch-AgentHealth-N.log`

Session state: `%USERPROFILE%\.grok\agent-health\watch-{grok|cursor}-{slot}\state.json`.

## Repo docs

| Document | Purpose |
|----------|---------|
| [docs/operator-playbook.md](docs/operator-playbook.md) | Full operator contract |
| [docs/feature-request-document-agentmonitor-2026-09-23.md](docs/feature-request-document-agentmonitor-2026-09-23.md) | FR / acceptance |
| [docs/build-and-test-plan-document-agentmonitor-2026-09-23.md](docs/build-and-test-plan-document-agentmonitor-2026-09-23.md) | Build plan for this doc work |

**Session rotate / hang (FR #99):** before resume, archive oversized Grok sessions (default 10 MB `updates.jsonl`, never delete). Hung `-p` with no CPU progress for `-SessionHangMinutes` (default 3) is stopped once, session rotated, and the pending FROM redelivered once. Complements FR #91 wake queue/timeout.

**Workspace (FR #102):** resolve `\ai` on fixed local disks only, letter order **C, D, E, …**. Explicit `-Cwd` wins. Bootstrap log: `%TEMP%\Watch-AgentHealth-start.log`. Tray passes `-Cwd` and surfaces early exit.

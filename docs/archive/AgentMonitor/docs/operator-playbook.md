<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/operator-playbook.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# AgentMonitor operator playbook

**Feature request:** [Issue #1](https://github.com/SimonBarnett/AgentMonitor/issues/1). **MRB:** [Issue #3](https://github.com/SimonBarnett/AgentMonitor/issues/3) (Bob chairs). This document does **not** stamp ready for human UAT.

AgentMonitor is `Watch-AgentHealth.ps1` plus `.cmd` launchers in this repo. It starts a **watch-seat** Grok or Cursor agent, keeps the agent process healthy, and forwards IRC traffic into that session. The agent still owns IRC per `agentic-irc` while the TUI is up. When the TUI exits (any reason), the monitor writes `$IrcHome/quit.req` so `irc_agent` PARTs every watch channel and QUITs before a later TUI may JOIN again. The monitor does not PART talk-seat / bobiverse homes.

---

## What it does

| Responsibility | Owner |
|----------------|--------|
| Start `agent.exe` (Grok) or `agent.cmd` (Cursor) TUI | Monitor |
| Persist session id; resume without reloading all skills | Monitor (`~\.grok\agent-health\state-{grok\|cursor}.json`) |
| Connect to IRC (`irc_agent`, `irc_listen` per skill) | Agent |
| Tail IRC debug log and inject `FROM` lines into the session | Monitor |
| Health-check / restart crashed agent tree | Monitor |
| Start, stop, or health-check `irc_listen` | **Not** the monitor |

The **watch worker** (`-WatchWorker`) runs the monitor loop. Visible by default (no `on` flag): the worker console stays visible and IRC `irc-in` / `forward` lines echo there; the Composer / Grok TUI opens in a normal window. **`-Windows off`** hides the worker and agent TUI; the log file still receives lines. One-shot `agent -p` forwards stay hidden.

---

## Grok vs Cursor

| Switch | Binary | IRC home default |
|--------|--------|------------------|
| `grok` | `agent.exe` | `%USERPROFILE%\.agentic-irc-watch-grok` |
| `cursor` | `agent.cmd` | `%USERPROFILE%\.agentic-irc-watch-cursor` |

Pass exactly one of `-Grok` / `-Cursor` (or `grok` / `cursor` on the main `.cmd`).

---

## Loop seat (non-job continuous agent, FR #103)

For agents that must **not** join the fleet job loop (example: ce-dayworks on CE-PRIORITY-DEV1):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Watch-AgentHealth.ps1 `
  -Grok -New -SeatType loop `
  -Channel '#ce-priority-dev1' -Nick 'dayworks-dev1' `
  -IrcHome "$env:USERPROFILE\.agentic-irc-watch-dayworks"
```

- `-SeatType loop` implies `-NoBored`: monitor never posts `!bored`.
- Brief/prompt has no ASSIGN / ACK / DONE-to-Jeeves instructions.
- `-Nick` must **not** match `{machine}-{pid}` (Jeeves only trusts that grammar for assign/busy).
- Still: health, crash-backoff, IRC FROM forward for that channel only.

Default fleet seats are unchanged (`-SeatType fleet`).

---

## Resume vs `new`

- **Default / `new` (CAST IRON for UI):** Desktop shortcuts, tray Agents / TipForm agent icons, and `Watch-AgentHealth.cmd <kind>` without `resume` always start a **fresh** `sessionId` with full skills + seed prompt. Legacy `*Resume*` shortcut **names** still pass `-New`.
- **`resume` (CLI only):** reuses the stored `sessionId` so the agent resumes the same session and does not reload all skills from scratch. Opt-in recovery only — never used by Desktop links or the Bob Fleet tray.
- For Cursor `-New`, only leftover nodes from the **previous watch session** and hung `forward-cursor.ps1` / orphan `worker-server` processes are pruned. Fleet `Git task` / `long-running-background-tasks` nodes and other TUIs are left alone. If Composer fails to stay up (OOM / missing node), the watcher switches to print-only and does **not** relaunch a TUI every poll.

Examples (from repo root):

```bat
Watch-AgentHealth.cmd grok
Watch-AgentHealth.cmd grok new
Watch-AgentHealth.cmd cursor
Watch-AgentHealth.cmd cursor new
Watch-AgentHealth.cmd grok off
Watch-AgentHealth.cmd cursor new off
```

Visible by default. **No `on` flag.** `off` hides the watch console and agent TUI. `new` and `off` may be in either order.

One-click equivalents and Desktop shortcuts are **`-Windows off`**: `wscript` + `Run-Hidden.vbs` so there is **no console window** and no agent TUI:

| File | Effect |
|------|--------|
| `Watch-AgentHealth-Grok-Resume.cmd` | Grok, always `-New` (legacy name) |
| `Watch-AgentHealth-Grok-New.cmd` | Grok, `new` |
| `Watch-AgentHealth-Cursor-Resume.cmd` | Cursor, always `-New` (legacy name) |
| `Watch-AgentHealth-Cursor-New.cmd` | Cursor, `new` |

---

## IRC: own watch home only

**LOCKED** — use only the watch IRC homes (next free slot on each launch):

- `%USERPROFILE%\.agentic-irc-watch-grok` (+ `-2` … `-16`)
- `%USERPROFILE%\.agentic-irc-watch-cursor` (+ `-2` … `-16`)

Pass `-IrcHome` only to pin a slot. Default binds the next home with no live
`Watch-AgentHealth -WatchWorker`. Orphan python/nodes pruned for **that slot
only** on start.

**Forbidden** (monitor refuses `-IrcHome` pointing here):

- `%USERPROFILE%\.agentic-irc-cursor`
- `%USERPROFILE%\.agentic-irc-cursor-2`
- `%USERPROFILE%\.agentic-irc-bobiverse` (bobiverse Watch / talk-seat home)

Do not point the watch seat at another agent’s IRC home.

### `irc.log` and `FROM` forwarding

1. The agent writes IRC debug lines to **`$IrcHome\irc.log`** (agent firehose).
2. The monitor tails `irc.log` (does not duplicate `irc_listen` or TSR as a second listener).
3. Each new **PRIVMSG** line is parsed; eligible messages become a single line:

   `FROM <nick> <target> <text>`

   and are resume-forwarded into the agent session.

4. On first tail after start/resume without a saved offset, the monitor begins at **end of file** (no backlog flood).

Filtered out (not forwarded): server numeric replies, raw `PING …` lines (in `Convert-IrcRawLineToFromLine`), certain MOOT/AGPK/ACTION patterns there, and in `Test-DropIrcLine` spaced tokens ` POINT `, ` DIGEST `, ` AGPK `, ` SEAL `, and case-sensitive ` PING ` (with trailing space). Bare chat `ping` / `PING` (whole body) **or** addressed `nick: ping` /
`ping nick` is answered by the watcher with `PRIVMSG … :nick: pong` on
`outbox.txt` and is **never** forwarded to the agent (no interrupt — busy
seats still pong). `ping me` and other non-ping text still forward (issue #7).
Server raw `PING` lines stay dropped in `Convert-IrcRawLineToFromLine`
(protocol; `irc_agent` handles server PONG).

**LOCKED:** This seat does **not** send `!bobiverse`. Agents follow `agentic-irc` for Ergo join/talk from this home.

---

## Workspace (`-Cwd`)

Default working directory is **`\ai` on the first available drive D: through Z:** (use existing folder or create `\ai`). The monitor does **not** default to `C:\` unless the operator passes **`-Cwd`** explicitly.

---

## Launch on Restricted ExecutionPolicy

**LOCKED:** Running `.\Watch-AgentHealth.ps1` directly often fails when policy is **Restricted**.

Use:

- Any `Watch-AgentHealth*.cmd` in this repo (they call `powershell.exe -NoProfile -ExecutionPolicy Bypass`), or
- An equivalent manual invoke with `-ExecutionPolicy Bypass`.

The main wrapper passes `-WatchWorker`. Visible launch runs the worker in the console (`-NoExit` so startup errors stay on screen). **`-Windows off`** starts a hidden worker (`-WindowStyle Hidden`).

---

## Logs and state (not in git)

| Item | Default location |
|------|------------------|
| Monitor log | `%USERPROFILE%\Desktop\Watch-AgentHealth\Watch-AgentHealth.log` |
| Session state | `%USERPROFILE%\.grok\agent-health\state-grok.json` or `state-cursor.json` |
| Worker pid file | `%USERPROFILE%\.grok\agent-health\watch-worker-{grok\|cursor}.pid` |

Override monitor log with `-LogPath` when invoking the script directly (advanced).

Do not commit logs, state files, IRC homes, or secrets.

---

## What this repo does **not** do

- Stamp **ready for human UAT** (workers do not stamp UAT).
- Send **`!bobiverse`** from the watch seat.
- Manage bobiverse **Watch** (`Watch-BobAgents` / bobiverse IRC home).
- Document or ship Desktop shortcut **icon paths** (see UNKNOWN below).

---

## LOCKED vs UNKNOWN

### LOCKED (script header + FR 2026-09-23)

1. `--grok` / `--cursor` switch (`agent.exe` vs `agent.cmd`).
2. Persist session id; `new` = fresh session.
3. Monitor does not start/stop/health-check `irc_listen`.
4. Tail `$IrcHome/irc.log`; forward PRIVMSG as `FROM` into the agent session.
5. Own IRC home only (`.agentic-irc-watch-*`); forbidden homes listed above.
6. Launch via `.cmd` / `-ExecutionPolicy Bypass` on Restricted policy boxes.
7. Workspace `\ai` on D:..Z: unless `-Cwd` passed.
8. No UAT stamp; no `!bobiverse`.
9. Main `.cmd` is visible by default (no `on` flag). One-click shortcuts start hidden (`-Windows off`). One-shot `agent -p` forwards stay hidden.

### UNKNOWN

- Exact Desktop shortcut icon paths on each fleet machine (UNKNOWN; repo `shortcuts/*.lnk` are generated per machine by `tools\Publish-DesktopShortcuts.ps1` and gitignored, so only `shortcuts/README.md` is tracked).
- Whether Desktop copies on flamingo / marchhare / ionos match commit `1a09848` or later SHAs.

---

## Optional script parameters

For operators who invoke `Watch-AgentHealth.ps1` with Bypass (not typical day-to-day):

- `-IrcHome` — must not be a forbidden home.
- `-Cwd` — explicit workspace.
- `-PollSeconds` (default 15), `-CrashBackoffSeconds` (default 20).
- `-LogPath` — alternate monitor log file.
- `-Windows off` — hide both terminals (default is visible).

Entry via the main `.cmd` includes `-WatchWorker`. With `off` (or any one-click shortcut), a hidden worker starts and the launcher exits. Otherwise the worker runs in the visible console.

**Skills** (what the monitor vs watch-seat agent do): `.grok/skills/agent-monitor/SKILL.md`, `.grok/skills/watch-seat/SKILL.md`.

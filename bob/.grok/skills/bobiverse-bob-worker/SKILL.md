---
name: bobiverse-bob-worker
description: >
  How to start and operate a bob WORKER agent: tray Agent click, bob-worker.exe command line, automatic cursor->grok->key-prompt selection, CWD <ai root>\bob\worker, always-new agent rule, IRC relay, ping/pong, IRC-loss exit, hang restart, logs, troubleshooting. Use when starting, debugging or changing the worker.
---

# bobiverse bob - worker agent (bob-worker.exe)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

Everything about starting and running a **worker agent** from the bob install (`<ai root>\bob`). The worker is one compiled program,
`<ai root>\bob\worker\bob-worker.exe`, that starts ONE agent, keeps ITS OWN IRC connection and feeds IRC messages into that agent.

## Start it (three ways)

1. **Tray: click `Agent`** (Bobiverse tray, notification area). It is a single menu item - there is NO sub-menu. One click = one NEW
   worker agent in ONE window (below). The tray copies `bob-worker.exe` to `%LOCALAPPDATA%\Bobiverse\worker\bin\bob-worker-<hash>.exe` and runs that copy (visible console), so
   an MSI upgrade/uninstall never finds the installed exe locked and never disturbs a running seat.
2. **Command line** (PowerShell, any time; same thing the tray runs):
   `& <ai root>\bob\worker\bob-worker.exe --mode agent --install-root <ai root>\bob --machine-id <machine>`
   (`--machine-id` defaults to `BOB_MACHINE_ID`, then the computer name; add `--echo` to also print the log; `--no-tls` is for tests only).
3. **Selection preview, starts nothing**: `& <ai root>\bob\worker\bob-worker.exe --mode agent --dry-run` prints JSON
   (`decision`, `reason`, the fuel readings, the cwd).

`--mode plan` is the plan variant (see skill `bobiverse-bob-plan`).

## ALWAYS a NEW agent (CAST IRON, t765u)

Every launch - tray click, command line, or the automatic restart after a hang - starts a **fresh agent**: new session id, new run folder, and (per click) its own single window. The exe never passes `--resume`, `--continue`, `-r` or `-c`, never attaches to or reuses an existing window or process
(`assert_fresh()` refuses such a command line). A second click makes a second, independent agent with its own IRC nick.

## ONE window per worker (t771u)

`bob-worker.exe` is a console program and **its console window is the agent's window**. The agent (Cursor TUI or Grok TUI) is started as a child that *inherits that console*
- there is no second console, no separate watcher window, no hidden helper window. The IRC connection, the relay, `!bored` and the health checks run as threads of the same exe. One tray `Agent`
click = one `bob-worker.exe` = one window. `Plan` is the same (`--mode plan`, no IRC).
* **Ending the exe ends the agent**: closing the window, `Ctrl+Break`-ing the exe, killing it or IRC loss all end the agent tree it started (a kill-on-close job object covers a hard kill of the exe, so no orphan agent).
* **The agent ending ends the exe** (exit 0; IRC QUIT).
* Ctrl+C is the agent's own key (the exe ignores it). The relay types into this same console's input, so you can also type in the window yourself.
* The Grok key prompt (when no tokens remain) appears **inside this same window**, input hidden - no dialog.

## Which agent starts - automatic, by token availability (never a menu choice)

1. **Cursor** `agent.cmd` (`%LOCALAPPDATA%\cursor-agent\agent.cmd`) when the **high-cost-models OR the auto (low-cost) pool** has more than 0 % left.
2. else **Grok** `agent.exe` (`%USERPROFILE%\.grok\bin\agent.exe`) when the local weekly reading (`unified.jsonl`, Grok 1.0.41 may report no % but a verified
   local login + current weekly period = available) shows tokens.
3. else a **prompt in the worker window** asks for an `XAI_API_KEY` for this start only (hidden input): kept in memory, handed to the child's environment, never written to disk, never printed or
   logged. Cancel = nothing starts (exit 4).

An unknown reading is "not available" (falls through), never "available". Readings come from `<ai root>\bob\tools\Get-BobAgentFuel.ps1` (the tray's own local readers:
`Get-BobCursorAgentWeeklyRemaining` via `Get-CursorAgentUsage.py`, `Get-BobWeeklyRemaining`, `Get-BobGrokAvailability`; no digest GET).

## What the worker agent gets

* **CWD `<ai root>\bob\worker`** and a first instruction to read the skills in `<ai root>\bob\worker\.grok\skills` and `<ai root>\bob\worker\AGENTS.md`
  (`bobiverse-worker-seat`, `bobiverse-bob-worker`, `harvest`; the CAST IRON harvest rule is at the top of each).
* Grok: `agent.exe --no-auto-update --no-alt-screen --cwd <worker> -s <new-uuid> --rules <text> <prompt>`.
  Cursor: a generated launcher reads the prompt from a file (IRC text never lands on a command line) and runs `agent.cmd --trust --force --workspace <worker> -- $prompt`.

## IRC (owned by the exe, not by the agent)

* Nick `<machine>-<pid>` (the exe's own pid, the talk-seat rule in `talk_seat_pid.py`); joins **only `#<machine>`**; speaks only there (FR #224: never PRIVMSG a nick or `#bobiverse`).
  Registration: TLS to `irc.ntsa.uk:6697` with the Ergo server PASS (found like the ear's: `home\ergo.password`, `config\ergo.password`, `BOB_IRC_PASSWORD`); SASL only if
  `BOB_IRC_SASL_USER`/`BOB_IRC_SASL_PASSWORD` are already in the environment. The seat does NOT use the ear's NickServ account.
  After numeric `001`, the exe **must** `JOIN #<machine>` and wait for the JOIN echo before starting the agent / posting `!bored`. A nick that is registered but not in the shop is deaf to Jeeves assigns (WHOIS has no `319` channels).
* **Event-driven relay**: a blocking socket read thread receives a line and injects it into the agent's console input from that same thread (WriteConsoleInput into the
  shared worker console) - no poll, no timer. The agent sees `FROM <nick> <target> <text>` as typed input. Ordering/limits: max 8 injections per 30 s, extra messages are
  coalesced into one `FROM (flood-coalesced N messages) ...`; identical consecutive lines are dropped; `POINT/DIGEST/AGPK/SEAL`, `is busy.`, `password=`, `XAI_API_KEY` lines are
  never relayed; messages arriving during the 6 s agent start-up are held and injected the moment it is ready. PMs are relayed only from `Jeeves`.
* **Liveness answered by the exe**: server `PING`->`PONG` at once, CTCP PING/VERSION, and the fleet `ping` / `ping <selector>` in `#<machine>` -> `pong` (selector matches the
  nick or the machine id; prefix/substring/`*`/`?`). Pings are never forwarded to the agent (no wake, no flood).
* **Reply path**: the agent appends `PRIVMSG #<machine> :text` (or plain text) lines to the `outbox.txt` named in its first instruction
  (`%LOCALAPPDATA%\Bobiverse\worker\run\worker-<machine>-<pid>-<id>\outbox.txt`); lines for any other target are refused.

## If IRC is lost: the seat ends (no reconnect loop)

On EOF, socket error, server `ERROR`, KICK, or a ping timeout (no data for 90 s, then a client PING unanswered for 45 s) the exe **kills the agent process tree it started - and only that
tree - then exits with code 3**. It never reconnects and never leaves an orphaned agent. Start a new seat with the tray `Agent` click. If IRC cannot be reached at start (exit 2) NO agent is
started. Closing the agent window by hand ends the seat too (exit 0, IRC QUIT).

## Agent health (while connected)

Sampled every 5 s over the agent's own process tree. **Hung** means: input was injected and the tree then shows no CPU/IO activity at all for 300 s ("no output / heartbeat"; the "not responding window" rule only applies if the agent owns a GUI window). An idle agent that is just waiting for input is NOT hung. A hung agent is killed (its tree) and replaced
by a **NEW agent** (never a resume) after a backoff of 5 s, then 15 s, then 45 s; at most 3 restarts per 30 min - the 4th hang ends the seat (exit 5). Every restart is logged
(`HUNG (<reason>); restart n/3 after Ns backoff`), and the message that was in flight is re-delivered to the new agent.

## `!bored`, ACK and DONE (the program posts `!bored`, you write ACK/DONE)

The exe posts `PRIVMSG #<machine> :!bored` itself - **never the model** - exactly like the agent watcher (`Watch-AgentHealth`, FR #100): when the agent is ready (seat start),
immediately after a DONE or NACK/GIVEUP (`bored -> shop reason=done|free`), and while idle (first after 120 s of quiet, then every 180 s). Never while busy: busy = an open `ACK`
with no DONE/NACK/GIVEUP (younger than 45 min), or the agent starting/restarting/hung. Outbox drain applies ACK/DONE/NACK/GIVEUP busy bookkeeping even when `irc.say` fails (FR #161),
and logs `bored: free-rx matched (...)`. Any forwarded message or outbox activity resets the idle clock; at most one `!bored` per second. It stops for good on IRC loss/shutdown.
A `!bored` written by the agent into `outbox.txt` is refused. Jeeves answers by assigning in `!focus` order; you ACK; DONE/NACK/GIVEUP mark the seat idle. Exact lines: skill
`bobiverse-bob-job-irc`; per job type: `bobiverse-bob-job-fr`, `bobiverse-bob-job-mrb`, `bobiverse-bob-job-uat`.

## Exit codes

`0` agent closed / window closed - `2` IRC unreachable at start - `3` IRC lost - `4` no agent possible or key prompt cancelled - `5` hang-restart limit - `6` launch failed - `64` bad usage (worker folder missing).

## Logs

* `%LOCALAPPDATA%\Bobiverse\worker\logs\bob-worker-agent.log` (start-up selection) and `...\run\worker-<machine>-<pid>-<id>\worker.log` (everything the seat did: IRC, injections, restarts).
* The tray log (`Open log`) records `worker: started ...` / `plan: started ...`.
* Never paste a key; the logs never contain one (values after `password=`/`token=`/`XAI_API_KEY=` are redacted).

## Upgrade / uninstall / seats

The MSI installs `worker\bob-worker.exe`, `worker\AGENTS.md`, `worker\.grok\skills\*`, `plan\...`; the self-updater and `Sync-BobiverseFromRepo.ps1` refresh them. Running seats use the
per-user run copy, so replacing the installed exe never kills or locks a seat; an uninstall leaves running seats alone (they end when their IRC link or window ends).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Click does nothing | `Open log` -> `worker: exe missing` = bob MSI older than this feature; reinstall. `--dry-run` shows what would start. |
| Key prompt appears although you have tokens | the reading is unknown/stale: run `tools\Get-BobAgentFuel.ps1 -InstallRoot <ai root>\bob` and read the JSON (`null` = unknown). |
| Exit 2, no agent | Ergo PASS missing/wrong or `irc.ntsa.uk:6697` unreachable; check `worker.log` (`IRC refused (464)` = bad PASS, `433` = nick clash - start again). Also `IRC JOIN #<machine> timed out` / `IRC JOIN refused (NNN)` = registered but shop join failed. |
| Nick online but Jeeves cannot assign / Halloy NAMES missing worker | Seat registered without JOIN (pre-fix) or JOIN failed. Confirm WHOIS has `319 #<machine>` and `worker.log` has `irc: JOIN` then `irc: joined` before `bored -> shop`. Rebuild/hotpatch `bob-worker.exe` and tray-Agent a new seat. |
| Exit 3 soon after start | IRC dropped; this is by design. Check Ergo/network; start a new seat. |
| Two windows appear for one click | should never happen: report it (intake). The agent must be a child of the exe's console; look for `CREATE_NEW_CONSOLE` in `worker.log` / a second `bob-worker.exe`. |
| `!bored` never posts | open ACK without DONE/NACK/GIVEUP (busy), agent restarting, or IRC lost. Look for `bored -> shop` / `bored: free-rx matched` / `bored: not sent` in `worker.log`. |
| Messages do not reach the agent | agent not ready yet (6 s) or `inject failed` in `worker.log`; raw-mode TUIs may need the window to exist - never minimise-kill the console. |
| Agent restarted repeatedly | `HUNG` lines in `worker.log`; after 3 restarts in 30 min the seat ends (exit 5). |
| Wrong agent chosen | selection is automatic; fix the fuel readings, do not edit the exe. |

File every problem you find: CAST IRON rule at the top.

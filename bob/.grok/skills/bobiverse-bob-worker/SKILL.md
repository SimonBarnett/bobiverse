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
* **Ending the exe ends the agent**: closing the window, `Ctrl+Break`-ing the exe, or killing it ends the agent tree it started (a kill-on-close job object covers a hard kill of the exe, so no orphan agent). **FR #3456:** IRC loss keeps the agent during reconnect grace; only grace exhausted (or `BOB_WORKER_IRC_RECONNECT_GRACE_S=0`) ends the tree with exit 3.
* **External kill parent log (FR #1643 / harvest #1678):** after `proc.wait()` the OS parent is usually gone - capture the create-parent cmdline at `start_agent` time and log it on unexpected exit (`terminated-by-external-kill`). Do not expect `parent_of` after wait to still resolve.
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
* Grok: `agent.exe --no-auto-update --no-alt-screen --cwd <worker> --disallowed-tools ask_user_question -s <new-uuid> --rules <text> <prompt>`
  (FR #3623: headless agent seats must never block on interactive `ask_user_question`; plan/monitor/maintenance omit the deny).
  Cursor: a generated launcher reads the prompt from a file (IRC text never lands on a command line) and runs `agent.cmd --trust --force --workspace <worker> -- $prompt`.

## IRC (owned by the exe, not by the agent)

**FR #1002:** after numeric `001`, the seat must `JOIN #<machine>` and wait for the JOIN echo (`irc: JOIN` / `irc: joined` in worker.log) before `!bored`. A nick that is registered but has no WHOIS 319 channels is deaf to shop assigns.


* Nick `<machine>-<pid>` (the exe's own pid, the talk-seat rule in `talk_seat_pid.py`); joins **only `#<machine>`**; speaks only there (FR #224: never PRIVMSG a nick or `#bobiverse`).
  Registration: TLS to `irc.ntsa.uk:6697` with the Ergo server PASS (found like the ear's: `home\ergo.password`, `config\ergo.password`, `BOB_IRC_PASSWORD`); SASL only if
  `BOB_IRC_SASL_USER`/`BOB_IRC_SASL_PASSWORD` are already in the environment. The seat does NOT use the ear's NickServ account.
* **Event-driven relay**: a blocking socket read thread receives a line and injects it into the agent's console input from that same thread (WriteConsoleInput into the
  shared worker console) - no poll, no timer. The agent sees `FROM <nick> <target> <text>` as typed input. Ordering/limits: max 8 injections per 30 s, extra messages are
  coalesced into one `FROM (flood-coalesced N messages) ...`; identical consecutive lines are dropped; `POINT/DIGEST/AGPK/SEAL`, `is busy.`, `password=`, `XAI_API_KEY` lines are
  never relayed; messages arriving during the 6 s agent start-up are held and injected the moment it is ready. PMs are relayed only from `Jeeves`.
* **NACK of a second assign (FR #1732):** free-rx / harvest hold only for NACK/GIVEUP/DONE that match the open ACK job id; concurrent NACK while another ACK is open keeps the seat busy.
* **Inject paste (FR #2498 / #1601 / #3894)**: paste the FROM line via clipboard+Ctrl+V. `OpenClipboard` retries (~20 x 25ms) so rdpclip races do not silently fail. On clipboard failure for a normal (long) Jeeves line, **do not** fall back to per-char KEY_EVENTs (that is the #2498 drip) — log `relay: inject path=fail` and hold/retry. Opt out: `BOB_WORKER_INJECT_PASTE=0` forces KEY_EVENT batch only. Logs `relay: inject path=paste|keys|fail`. Then wait BOB_WORKER_SUBMIT_GAP_S (default 0.20s) and Enter twice so the TUI submits. Live seats need a rebuilt bob-worker.exe (Build-BobWorker / MSI) - source-only patches do not update the frozen PyInstaller binary.
* **Submit verify (FR #2696 / #2791)**: after paste+Enter, probe grok `events.jsonl` `turn_started` / `unified.jsonl` `prompt.enqueue` for this session/pid; if no submit within `BOB_WORKER_SUBMIT_VERIFY_S` (default 3s), send **Enter only** (never re-paste) up to `BOB_WORKER_SUBMIT_VERIFY_RETRIES` (default 3) with backoffs 3/5/8s. Logs `relay: submit-verify ok|retry=n|FAILED`. Stop early only when an open ACK is for the **injected** job (`assign_job_ref` / `ack_job_ref`); an unrelated open ACK must not skip retries. Opt out: `BOB_WORKER_SUBMIT_VERIFY=0`. Async so the IRC relay thread is not blocked. Needs rebuilt `bob-worker.exe`.
* **Stale build notice (FR #2782 / FR #3180)**: a hotpatch only replaces `<root>\worker\bob-worker.exe`; a running seat keeps its `bob-worker-<sha12>.exe` run copy. At the idle `!bored` point (never mid-job) the exe compares sha12 of the install exe with its own name and, if different (install settled 60s), logs `worker: stale build (...) - keep running; restart me manually (FR #3180)`, announces on the shop, and skips `!bored` (no new work on the old build). It does **not** exit `8` - seat starts are manual only. Opt out: `BOB_WORKER_STALE_BUILD_RECYCLE=0`. **FR #3010:** a seat already silent from FR #2996 (stale `_release_gen`, never reaches idle `!bored` / `post_bored`) will **not** reach this notice after a hotpatch - stop that seat's tree by PID (no open job) and start a new seat manually (tray Agent / `!startworker`).

* **Liveness answered by the exe**: server `PING`->`PONG` at once, CTCP PING/VERSION, and the fleet `ping` / `ping <selector>` in `#<machine>` -> `pong` (selector matches the
  nick or the machine id; prefix/substring/`*`/`?`). Pings are never forwarded to the agent (no wake, no flood).
* **Reply path (FR #2380)**: the agent appends `PRIVMSG #<machine> :text` (or plain text) lines to `$env:BOB_OUTBOX` (bob-worker sets it on every agent child) or the path in the first instruction / each injected `FROM ... [outbox: <path>]` footer
  (`%LOCALAPPDATA%\Bobiverse\worker\run\worker-<machine>-<pid>-<id>\outbox.txt`). **Never** the ear's `home\outbox.txt`. Lines for any other target are refused.

## If IRC is lost: reconnect with grace (FR #3456)

On IRC loss the seat **keeps the agent** and tries to reconnect with backoff for
`BOB_WORKER_IRC_RECONNECT_GRACE_S` (default **600** seconds / 10 minutes). Same nick, shop
`#<machine>` only. Outbox ACK/DONE lines that fail to send are **held and flushed** after
reconnect; the seat also re-sends ACK for the open job so Jeeves keeps the assignment.

When grace is exhausted the seat exits cleanly with code 3 (`EXIT_IRC_LOST`). Jeeves FR #3400
releases any orphaned accepted row on PART/QUIT. Set `BOB_WORKER_IRC_RECONNECT_GRACE_S=0` for
the legacy behaviour (kill agent tree immediately, no reconnect).

**FR #2601 seat-heal:** clean `irc-lost` (exit 3) does not fire the crash hook. TipForm
`bob-tray.exe` Watchdog tops **agent** seats back up to the hard cap of 2 after a final exit.
Opt out heal: `BOBIVERSE_WORKER_SEAT_HEAL=0`.

## Agent health (while connected)

Sampled every 5 s over the agent's own process tree. **Hung** means: input was injected and the tree then shows no CPU/IO activity at all for 300 s ("no output / heartbeat"; the "not responding window" rule only applies if the agent owns a GUI window). An idle agent that is just waiting for input is NOT hung. A hung agent is killed (its tree) and replaced
by a **NEW agent** (never a resume) after a backoff of 5 s, then 15 s, then 45 s; at most 3 restarts per 30 min - the 4th hang ends the seat (exit 5). Every restart is logged
(`HUNG (<reason>); restart n/3 after Ns backoff`), and the message that was in flight is re-delivered to the new agent.

**FR #3623 ask_user pending:** a Grok `ask_user_question` that stays open (events.jsonl `tool_started` without `tool_completed`) leaves the process alive with ACK held, so HangDetector never fires. Agent launches deny that tool; if it still appears, after `BOB_WORKER_ASK_USER_PENDING_S` (default 60 s) the seat logs `stuck: ask_user pending <s>s`, sends Enter once (auto-answer), then after `BOB_WORKER_ASK_USER_ENTER_GRACE_S` (default 15 s) recycles with reason `ask-user-pending` (NEW agent; prior ACK void / job re-offered via re-deliver). Needs rebuilt `bob-worker.exe`.

## `!bored`, ACK and DONE (the program posts `!bored`, you write ACK/DONE)

The exe posts `PRIVMSG #<machine> :!bored` itself - **never the model** - (FR #100 / #1611 / #2802 / #2811 / #2834 / #2875): when the agent is ready (seat start), after DONE/NACK/GIVEUP **once the harvest hold ends**, and while idle (first after 120 s of quiet, then every 180 s). **FR #2802 (grok):** a session `events.jsonl` turn watcher releases the hold on `turn_ended` (and idle turn end posts reason `turn`); `harvest_hold_s` (default 90 s, `BOB_WORKER_HARVEST_HOLD_S`; outbox activity extends it) is the **fallback** when no turn-end signal arrives. Opt out: `BOB_WORKER_BORED_ON_TURN_END=0`. **FR #2834:** if a turn is still open after DONE (watcher saw `turn_started`, no `turn_ended` yet), keep holding past `harvest_hold_s` until `turn_ended` or `BOB_WORKER_TURN_HOLD_MAX_S` (default 600 s; logs `bored: turn hold max`); this also delays FR #2782 stale-build recycle at `post_bored`. **FR #2875:** `turn_ended` with the job ACKed but no DONE/NACK/GIVEUP arms done-miss (log `done-miss armed`); after `BOB_WORKER_DONE_MISS_GRACE_S` (default 20 s) inject one bob-worker reminder (do not check the drained outbox); if the reminder turn also ends with ACK still open, clear ACK and `!bored` reason `done-miss` (never invent a DONE verdict). **FR #2996:** that done-miss release must set `_release_gen = _turn_gen` (same as a normal turn-end release) so later `nak`/`idle` `!bored` are not gated forever; `_run` also clamps past-due waits to 0.5s so a stale gate cannot `wait(0)`-spin a CPU core. **FR #3012 / #3019:** mid-job `402 Payment Required` / `usage balance exhausted` / Cursor `NEEDS_AUTH` is out-of-fuel (not done-miss) — the exe GIVEUPs the open ACK with `out-of-fuel`, reports on the shop + digest, and holds quiet until fuel returns (Cursor: fuel-reading poll + optional log override). **FR #2811:** while the harvest hold is active (including the open-turn extension), Relay parks incoming Jeeves assigns (`held_until_turn_end`) instead of pasting mid-harvest; deliver on `turn_ended` or via `post_bored` flush at the harvest fallback (flush arms inject-pending and suppresses that tick's `!bored`). Never while busy: open `ACK` (younger than 45 min), inject-pending assign work until ACK/grace (`BOB_WORKER_ASSIGN_GRACE_S`, default 600 s), harvest hold, held assign with no pending done/free fire, or the agent starting/restarting/hung. Jeeves `nothing queued` resets the idle clock but does **not** arm inject-pending (MRB #1617); it **does** start the t817u `nak_s` timer (default 120 s, `reason=nak`) so the seat re-asks sooner than `repeat_s` 180 s (FR #2806) — still never injected (FR #2554). Outbox drain applies ACK/DONE/NACK/GIVEUP busy bookkeeping even when `irc.say` fails (FR #161), and logs `bored: free-rx matched (...)` / `bored: harvest hold` / `bored: turn ended ... hold released` / `relay: held assign until turn end`. Monitor/intake: idle+ungated during this hold is **not** starve (harvest #1665) - wait for `!bored`. At most one `!bored` per second. It stops for good on IRC loss/shutdown.
A `!bored` written by the agent into `outbox.txt` is refused. Jeeves answers by assigning in `!focus` order; you ACK; DONE/NACK/GIVEUP mark the seat idle. Exact lines: skill
`bobiverse-bob-job-irc`; per job type: `bobiverse-bob-job-fr`, `bobiverse-bob-job-mrb`, `bobiverse-bob-job-uat`.

## Exit codes

`0` agent closed / window closed - `2` IRC unreachable at start - `3` IRC lost - `4` no agent possible or key prompt cancelled - `5` hang-restart limit - `6` launch failed - `64` bad usage (worker folder missing).

## Logs

* `%LOCALAPPDATA%\Bobiverse\worker\logs\bob-worker-agent.log` (start-up selection) and `...\run\worker-<machine>-<pid>-<id>\worker.log` (everything the seat did: IRC, injections, restarts).
* The tray log (`Open log`) records `worker: started ...` / `plan: started ...`.
* Never paste a key; the logs never contain one. Crash/spool redact (FR #2411 / FR #2668 / FR #2679) covers `password=`/`token=`/`XAI_API_KEY=`, Bearer/Basic, NickServ IDENTIFY/REGISTER, IRC PASS, URL userinfo, and quoted JSON keys/values (including multi-word `"password": "a b c"`) — keep fake values only in tests.
* **Test fixtures (FR #3304):** never write realistic secret literals in tests (contiguous JWT headers, `Bearer` + JWT, `password=` hunter-style values). Build secret-shaped strings at runtime from parts (a-search: `tests/fixtures/fakeSecrets.js`) or use obvious placeholders (`FAKE_`, `EXAMPLE`, `xxxx`, AWS doc `AKIA…EXAMPLE`). Prefer fixing fixtures over force-pushing history to clear GitGuardian false positives.

## Upgrade / uninstall / seats

The MSI installs `worker\bob-worker.exe`, `worker\AGENTS.md`, `worker\.grok\skills\*`, `plan\...`; the self-updater and `Sync-BobiverseFromRepo.ps1` refresh them. Running seats use the
per-user run copy, so replacing the installed exe never kills or locks a seat; an uninstall leaves running seats alone (they end when their IRC link or window ends). Tray bin refresh **defers** delete of a hashed run-copy while exclusive-open shows it locked by a live seat (FR #1643 / #1678) - that defer is correct, not a stuck cleanup bug.

## Hard cap: IRC-joined agent seats only (FR #3181 / #2522 / #2667)

The hard max of **2** applies only to **agent** seats that have joined `#<machine>` on IRC. Plan, maintenance, monitor, and seats still at the key dialog (or still connecting) never count and are never refused. Shared registry: `%LOCALAPPDATA%\Bobiverse\worker\run\seats\<nick>.irc.json` (written after JOIN, cleared on PART/QUIT/irc-lost/exit). Readers: `common/scripts/worker_irc_seats.py`, tray `Measure-BobTrayIrcAgentSeats` / `CountIrcAgentSeats`, `startworker.decide`, `bob_worker.worker_cap_refusal`. Missing/unreadable `--mode` is **unknown**, never agent. Enforcement needs rebuilt `bob-worker.exe` + `bob-tray.exe` (not a safe live hotpatch).

## Hard cap recycle / seat roots (FR #2556 / t815u)

A PyInstaller onefile `bob-worker.exe` (or hashed `bob-worker-<hash>.exe`) is **bootloader + same-named child = ONE seat**. Process-root helpers still use `ParentProcessId` filters for heal/reclaim. When reclaiming over the hard max, **never** `Sort-Object ProcessId | Select -Skip N | Stop-Process` on a flat PID list — that destroys whole seats (MarchHare killed seat 38244/40460 after FR #2554 hotpatch). Use `worker_seat_roots` / `worker_seat_tree_pids` / `excess_worker_seat_roots` in `bob_worker.py`, and tray `Stop-BobWorkerSeatTrees` (root + children only). Cap *enforcement* for new agent starts is IRC markers (FR #3181), not process roots alone.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Click does nothing | `Open log` -> `worker: exe missing` = bob MSI older than this feature; reinstall. `--dry-run` shows what would start. |
| Key prompt appears although you have tokens | the reading is unknown/stale: run `tools\Get-BobAgentFuel.ps1 -InstallRoot <ai root>\bob` and read the JSON (`null` = unknown). |
| Exit 2, no agent | Ergo PASS missing/wrong or `irc.ntsa.uk:6697` unreachable; check `worker.log` (`IRC refused (464)` = bad PASS, `433` = nick clash - start again). |
| Exit 3 (IRC lost) | Grace exhausted after reconnect attempts, or `BOB_WORKER_IRC_RECONNECT_GRACE_S=0` (legacy immediate exit). Check Ergo/network/`worker.log` for `reconnect grace` / `grace exhausted`. Start a new seat manually (tray Agent / !startworker). Check `tray-lifecycle.log` for `seat-exit` / `not restarted` (FR #3180); rebuild `bob-worker.exe` after pull for FR #3456. |
| Two windows appear for one click | should never happen: report it (intake). The agent must be a child of the exe's console; look for `CREATE_NEW_CONSOLE` in `worker.log` / a second `bob-worker.exe`. |
| `!bored` never posts | open ACK without DONE/NACK/GIVEUP (busy), agent restarting, or IRC lost. Look for `bored -> shop` / `bored: free-rx matched` / `bored: not sent` in `worker.log`. After a `done-miss` release, if the seat stays silent and burns a core, suspect stale `_release_gen` (FR #2996) — needs rebuilt `bob-worker.exe` **and** a new seat: that silent state never reaches idle `!bored`, so FR #2782 stale-build recycle at `post_bored` never fires; after the hotpatch, stop the seat tree by PID (no open job) and start a new seat manually (FR #3010 / FR #3180). Mid-job `402 Payment Required` / `usage balance exhausted` is **out-of-fuel** (FR #3012): the exe must `GIVEUP … out-of-fuel` at once, report on the shop + digest, and stay quiet (no done-miss, no `!bored`) until fuel returns — never treat 402 as a missed DONE. |
| Seat ACKed then went quiet after Grok 402 / out of credits | Out-of-fuel (FR #3012). Look for `out-of-fuel: detected` / `out-of-fuel: posted GIVEUP` in `worker.log`. Rebuild `bob-worker.exe` with the FR #3012 watcher; until then force-stop the seat tree and start a new seat manually after fuel returns (FR #3180). |
| Cursor seat ACKed then stuck after pool hit 0 / NEEDS_AUTH | Out-of-fuel parity (FR #3019): same GIVEUP/quiet/digest contract as grok. Cursor uses mid-job fuel-reading poll (no unified.jsonl); optional `BOB_WORKER_OUT_OF_FUEL_LOG` for a log tail. Look for `out-of-fuel: watcher started (kind=cursor` / `mid-job fuel reading exhausted`. |
| Messages do not reach the agent | agent not ready yet (6 s) or `inject failed` in `worker.log`; raw-mode TUIs may need the window to exist - never minimise-kill the console. |
| `relay: injected` in `worker.log` but TUI waits for Enter | First-assign race on a fresh grok TUI (paste lands after Enter) or stale exe. Look for `relay: submit-verify retry=` / `FAILED` (FR #2696). Press Enter once to unblock this line; durable fix = rebuild exe with submit-verify + start a **new** tray Agent seat (harvest #1605 / FR #2696). |
| Agent restarted repeatedly | `HUNG` lines in `worker.log`; after 3 restarts in 30 min the seat ends (exit 5). |
| Seat died mid-job; need who killed it | Look for external-kill / create-parent log from FR #1643. Parent after `wait()` is empty by design - spawn-time cache is the evidence (harvest #1678). |
| Second seat dies after hotpatch recycle (no `shutting down` in worker.log) | Flat PID Skip-N kill (FR #2556). Reclaim with `excess_worker_seat_roots` + `Stop-BobWorkerSeatTrees`, never `Select -Skip N | Stop-Process`. |
| Wrong agent chosen | selection is automatic; fix the fuel readings, do not edit the exe. |

File every problem you find: CAST IRON rule at the top.


## PyInstaller pack verify (FR #2406)

Build-BobWorker / MSI ships a one-file PyInstaller bob-worker.exe. Do **not** fail a pack/UAT solely because outer-PE ASCII Select-String misses _OUT_FREE_RX / free-rx / reason=free — those live in the compressed PYZ (bob_worker.pyc). Verify with pyinstxtractor on the exe, or run bob/tests/test_bob_worker_bored_020.py free-rx tests / a scratch outbox GIVEUP and check worker.log for bored: free-rx matched and bored -> shop reason=free. Source-only edits do not update a running tray hashed copy; rebuild + new seat for live proof.

## Skill harvest backlog (FR #1682 / FR #1684) - consolidate by book, then PR

Harvest receipt rule: any receipt whose title or body says DONE, twin, duplicate, filed, or merged is closed by the worker/MRB as soon as it is filed; a receipt is never left open.

Chair **offers** `label:skill` / `harvest:` / `skill:` intake receipts as FR promote jobs (FR #1682). They are not product code FRs; do **not** GIVEUP. Workers consolidate by skill book and open one promote PR so MRB can merge lessons into `.grok/skills`.

When assigned a skill-promote job, or when you have `gh` write and open skill receipts for books you own:

1. Group open skill issues **by owner skill book** (`harvest-agent-skills` table).
2. **Close duplicate** receipts for the same book/lesson.
3. Open **one** `harvest/...` PR per book (or one multi-book PR with clear paths); body lists `Closes ...` and `Duplicates closed: ...`.
4. DONE with PR URL; another seat **MRB** merges. Never push `main`. Never one PR per harvest receipt.

Details: skills `harvest` + `harvest-agent-skills` (Worker: consolidate open skill receipts -> promote PR). Job wiring: `bobiverse-bob-job-fr`.

## Harvested reliability rules (closed skill records #1201-#1460)

Skill-intake consolidation: when a worker takes an FR from skill intake (label:skill / harvest), it must close all open issues for that skill book (every harvest/skill issue targeting the same book), open one consolidated PR for them, and cite every issue it closes (Closes #N for each); no per-issue PRs for the same skill book; the worker closes the issues itself as part of DONE.

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

- Treat `outbox.txt` as a durable hand-off: create its parent/file before a drain, append atomically, and never delete the file merely because one drain reached EOF. A later worker/relay must be able to recreate and append safely. See #1201 and the related harvest records.
- `IrcSeat.say()` must report a dead writer as failure and trigger the normal lost-IRC path; never log a successful send when `_write_loop` has already died. Confirm `001` + shop JOIN before posting `!bored`. See the worker-liveness lessons around #1018 and #1201.
- When diagnosing a silent seat, distinguish TCP/WHOIS presence from a confirmed JOIN and inspect the worker's own log/outbox; a registered nick without a shop JOIN is not assignable work.

## Harvest digest (lessons audit 2026-10-06)

Generalised from 21 harvested lessons that never reached this book (audit for FR #2705). The per-lesson table is in `common/docs/harvest-lessons-audit-2026-10-06.md`.

- **Seat inject and submit:** WriteConsoleInput success does not mean submitted. Use a submit gap (default 0.20s) plus a verified second Enter. Clipboard paste must restore the operator's clipboard. Hold inject and `!bored` until the first grok `turn_ended` after spawn (FR #2884; `startup_grace_s` fallback, `startup_min_s` floor). Treat inject as busy until ACK, and after DONE hold `!bored` for `harvest_hold_s` (90s, extended while the outbox has content). On an assign ACK miss, remind first, then recycle. Drains recreate an empty `outbox.txt`. Nothing-queued replies and outbox drains must log, so silence is never mistaken for a deaf seat. If submit verification misses, retry Enter only (never re-paste), and run the verify asynchronously so the IRC relay is not blocked. (9 lessons: harvest #1618, #930, #1008, #1077, #1029, #1022 +3 more, 3 held intake rows)
- **Tray and launch parity:** tray, TipForm, CLI and remote starts share one `bob-worker --describe-launch` plan (argv/cwd/BOB_*), with `prepare_seat_child_env` scrubbing `CURSOR_*`/`SAND_*` after the overlay. Normalize `--root` so the single-instance mutex matches. Recycle and cap-kill by seat roots (`recycle_to_cap`), never by PID order. Watchdog relaunch uses `-ForceNew -SkipTidy` and respects the operator-exit suppress file. Tray readers accept `.work`, `.job` and `.working_on`. Start-Bob prefers the freshly staged bob-ear.exe. `describe_worker_exe_launch` whitelists the maintenance/monitor modes (with `--work-root`) and raises on unknown modes, never silently mapping them to agent. The tray heartbeat (`tray.alive`) runs on a thread timer, never on a WinForms timer that shares the UI thread with the poll. (8 lessons: harvest #1669, #809, #2674, #2709, #2703, 3 held intake rows)
- **Fleet identity:** the fleet id is the registered fleet machine name; ionos's Windows COMPUTERNAME is WIN-MPRE8VI4U6U, which folds to ionos. Seat nicks are `machine-pid`, and `canonical_worker_nick` must parse them without the registry. The assign wire uses the full IRC nick, never a digest display alias. Unit tests must register machine ids, or seat parsing returns None. (4 lessons: harvest #1296, #1067, #1069, 1 held intake row)

## Harvested lessons (intake)

- bob-worker harvest: Invoke-BobiverseHarvest must prefer BOB_NICK then BOB_AGENT_NICK, and seat_env_extra must export both so lesson PR seat= stamps and self-MRB blocks the opener (FR #2790 / MRB #2795).
- bob-worker: BoredEmitter.turn_ended releases harvest hold when grok events.jsonl turn_ended arrives at/after DONE; harvest_hold_s is fallback only (FR #2802 / PR #2809).
- MRB bob-worker turn watcher: Supervisor path_fn must return grok_session_dir(...)/events.jsonl — returning the session dir makes GrokTurnWatcher path.is_file() fail forever (silent 90s harvest_hold fallback); pin with a source hostile test
- bob-worker: after GIVEUP/NACK/DONE, hold Jeeves assigns in Relay until turn_ended or harvest_hold_s fallback; post_bored flushes before !bored and arms inject-pending (FR #2811).
- bob-worker: when a post-DONE turn is still open, do not fire harvest_hold_s !bored (or stale-build recycle) until turn_ended or TURN_HOLD_MAX_S (FR #2834).
- bob-worker: turn_ended with ACK open and no DONE/NACK/GIVEUP arms done-miss remind then release (FR #2875); never invent DONE; ack_stale_s remains last resort.
- bob-worker: done-miss release must set `_release_gen = _turn_gen` or a prior normal turn-end leaves nak/idle gated forever and `_run` spins on `wait(0)` (FR #2996). A seat already stuck silent never reaches `post_bored` stale-build recycle — after hotpatch, stop the tree by PID and start a new seat manually (FR #3010 / FR #3180).
- bob-worker: mid-job agent `402 Payment Required` / `usage balance exhausted` is **out-of-fuel** — detect in unified.jsonl, `GIVEUP <job> out-of-fuel` immediately, digest `status=out_of_fuel`, suppress `!bored` until fuel returns; never wait for done-miss (FR #3012).
- bob-worker: Cursor (non-grok) gets the same out-of-fuel contract — start fuel watcher for `cursor` too; detect `NEEDS_AUTH` / out-of-tokens text; mid-job fuel-reading poll while ACK open when there is no Cursor unified.jsonl (FR #3019).

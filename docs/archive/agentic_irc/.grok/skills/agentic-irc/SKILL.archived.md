<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path .grok/skills/agentic-irc/SKILL.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: agentic-irc
description: >
  Join TLS IRC as an agent. Fleet/bobiverse uses private Ergo irc.ntsa.uk:6697.
  Secrets are TOFU-pinned DH-AAD boxes (not signatures; first AGPK for a nick
  wins). Use when the user says join IRC, Ergo, irc.ntsa.uk, Libera, agentic_irc,
  /agentic-irc, talk to another Grok on IRC, encrypt secrets for IRC, need
  an IRC listener so you get responses, Watch-AgentHealth preferred wake,
  or legacy talk-seat TSR. Also Start-TalkSeat, talk-seat nick, #88,
  PowerShell seat PID, two Cursor TUIs, why the second process fails,
  cursor-2, start a new cursor agent after a hung TUI close, extra channel
  JOIN, outbox JOIN-as-chat, Mode 3 PIN (never on #bobiverse), harvest that
  talk-seat playbook, everyone harvest your irc skill, recycle-after-merge
  after PASS-nits merge to main, or if anyone fails to pong restart them on
  that box. Fleet Ergo start/firewall/Watch-Bobiverse is skill bob-irc.
  Hung end/roll is killproc. Watch-seat create is watch-agent-health
  (agentic_build).
---

# agentic-irc

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_irc

TLS IRC. Status in clear. Secrets only as `SEAL v2` lines.

Fleet builders (`#bobiverse`): `irc.ntsa.uk:6697` (Let's Encrypt). PASS from env `AGENTIC_IRC_PASSWORD` or `~\.grok\ergo\connect.password`. Host/port live in `agentic_build/config/bobiverse.json`. See `agentic_build/docs/bobiverse.md`. Do not point any `bob-*` at Libera.

**CAST IRON (Simon 2026-09-29):** shop `#{machine}` / `bob-{machine}` use the box **Windows `COMPUTERNAME` lowercased** (`BOB_MACHINE_ID`), not a fleet marketing alias. Host `WIN-MPRE8VI4U6U` → `win-mpre8vi4u6u` / `bob-win-mpre8vi4u6u` / `#win-mpre8vi4u6u`. Do not invent `ionos` / `#ionos` / `bob-ionos` for that VPS. Named boxes (`flamingo`, `marchhare`, `ce-priority-dev1`) keep those ids only when installed as such.

Shop rooms are `#<machine-id>`. FR work talk room: `#agentic_irc` (Simon + talk seats; not `bob-*`). Not `#bob-<id>`.

| Nick pattern | JOIN (Ergo) | Notes |
|--------------|-------------|--------|
| `bob-<id>` | `#bobiverse` + `#{machine}` | Builders; first JOIN creates shop (`bob-win-mpre8vi4u6u` → `#win-mpre8vi4u6u`) |
| `{machine}-{pid}` talk seat | `#{machine}` **only** (CAST IRON 2026-09-25: workers never JOIN `#bobiverse`; irc_agent drops other channels and auto-PARTs them) | **`pid` = coordinator PowerShell `$PID`** (`Start-TalkSeat.ps1` / TSR — **not** python `irc_listen` / `irc_agent` PIDs). Default extras include `#agentic_irc` via script default `-Channel`. More rooms (`#airc-moot`, etc.) via `-Channel`. `channels_for_nick` always adds `#bobiverse` + shop for talk seats (issue #108); omitting fleet in `-Channel` does not opt out. Bobosphere is not talk-seat-forbidden. |
| `w-<shortid>-<pid>` worker | `#{machine}` only | Never `#bobiverse`. Spawn helper: `scripts/start_worker_irc_agent.py` (UTF-8) under `C:\ai\agentic_irc\scripts` or `D:\ai\agentic_irc\scripts`. Callers: `agentic_build` `Start-BobCursor` + `Start-BobWorker` after that install. |
| Jeeves `--chair` | `#bobiverse` + every shop | `--home` `~\.agentic-irc-jeeves`; `BOB_DIGEST_HOME` `~\.agentic-irc-bobiverse`. Do not share the bob ear `--home`. skill `bob-irc` |

Prefer `scripts/Start-TalkSeat.ps1 -MachineId <id>` (default `#bobiverse,#<machine>,#agentic_irc`). `coordinator.pid` **`seat=`** is authoritative; `listen=` / `agent=` are diagnostics only. Worker homes: `~\.agentic-irc-bobiverse\workers\<id>\<pid>`. **`working_on` / idle: webhook only** (`post_working_on.py` â€" never `PRIVMSG simon` or shop for status). Shop: conversation stdout. Open Query: thinking/tool traces only (not working_on). One voice: do not write the same line to `bob-*` and the session outbox. Secrets-shaped lines drop. Status read is `!bobiverse` (chair whisper) only â€" do not send `!report`. Digest chair facts: skill `bob-irc`. Mode 3 pairing PIN is never on `#bobiverse` (skill `invite-airc`). `bob-*` assigns idle workers with `PRIVMSG #{machine}`, not Query.

Other homes (Club Madeira, Mode 3 field) pass `--host` / `--port` as the chair specifies. `irc_agent.py` defaults to `irc.ntsa.uk:6697` if `--host` is omitted. Fleet Watch-Bobiverse always passes host/port from `bobiverse.json`.

`--nick` on `seal.py` is the **recipient** IRC nick, not yours.

This is not a signature. v2 binds DH to a TOFU-pinned AGPK. First AGPK for a nick wins.

## Live service tree (FR #213) â€" CAST IRON

MRB/FR workers must **never** `git checkout`, `git stash`, or `git reset` inside a
**live service checkout** that `irc_agent` / monitors load from (fleet:
`D:\ai\agentic_irc`, `C:\ai\agentic_irc`, or `AGENTIC_IRC_SERVICE_TREE`).

That wiped hotpatches on MarchHare (2026-09-25): stash + checkout of an MRB
branch left the seat on old code ->' nick-guard crash loop ~17s ->' Ergo IP throttle.

**Required worker path:**

1. `python scripts/temp_git_worktree.py --live-root <service> --ref <branch>`  
   or `temp_git_worktree.add_temp_worktree` / `run_mrb_checkout_flow`  
   (`git worktree add <tmp> <ref>` under `%TEMP%`, then remove).
2. Do all MRB/FR edits **only** in that temp worktree (or a separate clone under
   the seat work dir). Delete the worktree when done.
3. Startup guard: `irc_agent` and Watch-AgentHealth call `live_tree_guard` â€"
   WARN + `service-tree-warn.json` when the service tree is not on `main`, or
   when a stash is newer than the last start marker.
4. Monitor repair backoff: `monitor_restart_backoff` (exponential, capped) so a
   crash loop cannot reconnect-spam Ergo. Env:
   `AGENTIC_IRC_MONITOR_BACKOFF_BASE_S` (default 2),
   `AGENTIC_IRC_MONITOR_BACKOFF_CAP_S` (default 300),
   `AGENTIC_IRC_MONITOR_FAST_EXIT_S` (default 45).

Do **not** restart live monitors/agents from an implementer FR unless Bob
assigns recycle. Tests: `tests/test_live_tree_fr213.py`.

## Hard gate

Either clone `https://github.com/SimonBarnett/agentic_irc` and run from that tree, or:

```bash
python scripts/install_skill.py
```

that copies `SKILL.md` **and** `scripts/` into `$GROK_HOME/skills/agentic-irc/` (default `~/.grok/skills/agentic-irc`). Then invoke:

```bash
python ~/.grok/skills/agentic-irc/scripts/seal.py
python ~/.grok/skills/agentic-irc/scripts/irc_agent.py
```

Do not run `python scripts/seal.py` on a box that only has the leaflet SKILL.md.

```bash
pip install -r requirements.txt
python scripts/seal.py genkey
```

Two agents on one box **must** use different `--home` / `AGENTIC_IRC_HOME`. See `docs/multi-agent-one-host.md` in the repo (Libera vs Ergo, SASL, stdout redirect). Flamingo example: Watch `bob-flamingo` uses `~\.agentic-irc-bobiverse`; a talk session uses `--nick flamingo-<agentPid>` (`irc_agent` PID) `--home ~\.agentic-irc-cursor`. Extra sessions need their own home too. Do not reuse the Watch home. That extra `irc_agent` makes Watch think the builder is already up (skill `bob-irc`).

**Build-worker seats (Simon 2026-09-23):** create them **only** with Watch-AgentHealth (`watch-agent-health` / `Start-BobWatchWorker.ps1` / hidden Desktop shortcuts). Own `.agentic-irc-watch-*` home and own `irc_listen` (a shared listener copies every PRIVMSG into every client). Do **not** `Start-TalkSeat` / `cursor-2` / raw TUI to add a build worker. Talk seats stay talk seats.

Second **talk** TUI on the same box: `Start-TalkSeat.ps1 -MachineId <id> -IrcHome ~\.agentic-irc-cursor-2` (flamingo, `ce-priority-dev1`, others). Default `~\.agentic-irc-cursor` is the first talk seat. Same nick on Ergo ghosts the live connection â€" Halloy looks like "login kicks the other". Do not `Stop-Process` `irc_agent` / `irc_listen` on another seat's home. `Start-TalkSeat` refuses to steal a live `coordinator.pid` home.

## Other flamingo looks disconnected

Halloy "the other flamingo keeps disconnecting" is usually **deaf**, not gone.

Diagnose on flamingo:

1. Two Cursor windows: this chat `flamingo-<seatA>` home `~\.agentic-irc-cursor`; window **Agentic Build IRC** `flamingo-<seatB>` home `~\.agentic-irc-cursor-2`.
2. If both used `flamingo-17568` / the same home: second PASS ghosts the first (`QUIT` / nick vanish). Fix: different `--nick` and `--home` (above).
3. If `irc.log` has `001` + JOIN and **no** `QUIT` for that nick, the socket is up. `coordinator.pid` `listen=` empty means **no TSR** â€" they will not `pong`. That looks like disconnect.
4. `464` / `Password incorrect` = agent started without `AGENTIC_IRC_PASSWORD`. Relog with Start-TalkSeat (loads connect.password). Never print the secret.
5. Cursor foreground `irc_listen` dying `4294967295`: use detached listen (`Start-IrcTsr.ps1` / `Start-TalkSeat.ps1`) then tail `listen.stdout.log`. Do not kill the other home's listen.

Fix for the second window: `Start-TalkSeat.ps1 -MachineId flamingo -IrcHome ~\.agentic-irc-cursor-2` in **that** TUI, notify `^FROM ` on **that** home only. Do not write the first seat's `outbox.txt`.

Hung / deaf seat Simon wants ended: skill `killproc` (`Stop-HungAgent.ps1 -IrcHome Ã¢â‚¬Â¦ -Roll`). Never `-Home` (PowerShell `$Home` is read-only). Do not kill this TUI's home.

## Why the SECOND process fails

Simon started two Cursor processes per box (flamingo and DEV1
`ce-priority-dev1` included; not "except dev"). The second failed
on each until a distinct cursor-2 home. Two failure modes, not Ergo
kicking at random:

1. **Same nick.** Two TUIs both `flamingo-17568` (or both default home).
   Ergo one socket per nick: second PASS ghosts the first (`QUIT` /
   Halloy "login kicks the other").
2. **Same default home steal.** `Start-TalkSeat` with a new `$PID` on
   `~\.agentic-irc-cursor` used to `Stop-Process` the live agent+listen
   then start its nick. `#91` / `#90` hard-fails that steal
   (`talk_seat_pid.py --bind-home` exit 3). Second TUI must use
   `-IrcHome ~\.agentic-irc-cursor-2` in **that** window.

Deaf is the third lookalike: `001`+JOIN, `listen.stdout.log` has FROM,
but no Cursor TSR notify `^FROM` on that home â€" never `pong`. killproc
`-Roll` replaces python only; it does not attach the other TUI.

Working seat on a box restarts the hung *other* home (skill `killproc`).
If `~\.agentic-irc-cursor-2` is missing, there is no hung second seat
(marchhare seat-1 only). Do not WinRM.
Simon: if a nick **on this box** fails to pong, the live agent here
`killproc -IrcHome <their home> -Roll`. Do not roll this TUI's home.
Do not restart a nick that lives on another machine.

## Fleet harvest / restart failed pong

Simon on `#bobiverse` `everyone harvest your irc skill`: each talk seat
harvests IRC playbooks into this repo (skill `harvest-agent-skills`).
Do not wait for the hourly task. Empty harvest: no commit.

Simon `if anyone fails to pong ... restart them`: the *live* seat on
*that* box killproc-rolls the deaf home only. Do not restart a nick
that already ponged. Do not kill this TUI's home. Do not WinRM.

Second-seat runners (`Start-SecondSeatTui.ps1`, `_Run-SecondSeat*.ps1`)
must be **UTF-8** (no UTF-16). UTF-16 makes Windows PowerShell report
`AmpersandNotAllowed` on `&`. Write via `[IO.File]::WriteAllText(..., UTF8Encoding($false))`
or `Set-Content -Encoding utf8`. Stock `_Run-SecondSeatTui.ps1` is
flamingo-only; DEV1 uses `_Run-SecondSeatDev1.ps1` /
`bootstrap-second-seat-dev1.txt` (`-MachineId ce-priority-dev1`).

## Start a new cursor-agent (irc + build)

Simon: hung window gone / start another process with irc and build /
try again.

1. Do not steal `~\.agentic-irc-cursor` or this TUI's `agent.cmd` node.
2. If cursor-2 `irc_agent` is still JOIN, keep it. Else
   `scripts/Start-SecondSeatTui.ps1` (or `Start-TalkSeat.ps1 -MachineId
   <id> -IrcHome ~\.agentic-irc-cursor-2` in a **new** `-NoExit`
   PowerShell). Nick comes from `Start-TalkSeat` (`{id}-<irc_agent PID>` via
   `--auto-nick`), not a stale suffix from a dead agent.
3. Start visible `cursor-agent.ps1 --trust --force --workspace C:\ai
   --model grok-4.6 -- $prompt` where `$prompt` is read from a **file**.
   Do not pass the prompt on `cmd.exe /c` (spaces truncate). Do not `-p`.
4. Prompt: second seat; home cursor-2 only; arm `^FROM`; pong; skills
   agentic_irc + agentic_build; no UAT; no `!bobiverse`.
5. SendKeys only if foreground title is exactly `Agentic Build IRC` or
   `Flamingo Talk Seat`. Never Halloy (`#bobiverse â€" Halloy`).
6. Ping the new nick until `pong`.

## Start-TalkSeat recycle (#88)

On each box after pull (or when Simon says refresh / restart talk seats):

1. `git -C <agentic_irc> pull origin main`
2. `python scripts/install_skill.py`
3. Talk seat: `scripts/Start-TalkSeat.ps1 -MachineId <id>` (second TUI: also `-IrcHome ~\.agentic-irc-cursor-2`). Optional non-PowerShell spawn: `python scripts/start_talk_seat.py --machine <id>` (same `--auto-nick` rule). Script starts `irc_agent` with `--auto-nick` so nick `{id}-<agentPid>` matches the running agent PID, writes `coordinator.pid` `agent=`/`seat=`, loads Ergo PASS, starts listen TSR. Never use `irc_listen` PID as the suffix.
4. Recycle `bob-<id>` via Watch-Bobiverse only (skill `bob-irc`). No `--hello`. No `BobFleet-*` stop.
5. ACK on `#bobiverse` one line: `Start-TalkSeat.ps1 agent=<agentPid> nick=<id>-<agentPid> (irc_agent PID). bob-<id> up. pulled+install_skill.`

Example (marchhare): `marchhare ACK #88 â€" Start-TalkSeat.ps1 agent=19392 nick=marchhare-19392 (irc_agent PID). bob-marchhare up. pulled+install_skill.`
Example (marchhare talk-seat / #88 only - **not** Jeeves shop wire):
`PRIVMSG #bobiverse :Start-TalkSeat.ps1 agent=19392 nick=marchhare-19392 (irc_agent PID). bob-marchhare up.`
Shop FR/MRB/UAT ACK/DONE for Jeeves must start with `ACK`/`DONE` and `owner/repo#n` (see AgentMonitor FR #104 / bob-git-accept); never `nick: ACK` or `ACK #88`.

Raw `irc_agent.py` (no Start-TalkSeat) must set `AGENTIC_IRC_PASSWORD` from `~\.grok\ergo\connect.password` and pass `--nick {id}-{agentPid} --home <this seat only>`. Set **`AGENTIC_IRC_SEAT_PID={agentPid}`** (or `self` with `--auto-nick`) so the nick-suffix guard matches. Missing PASS is Ergo `464` / `ERROR :Password incorrect` â€" Halloy shows the nick gone. Missing `--nick` on a shared home steals or 464-loops. Never print the password. When restarting only the agent, do not `Stop-Process` the other seat's `irc_listen` (that kills their TSR).

Before connect, `irc_agent.py` runs `scripts/prior_irc.py` (also `Start-TalkSeat.ps1` / `Start-BobEar.ps1`). Fixed rules, no LLM: kill `irc_agent` with the same `--nick` or the same `--home`, and `irc_listen` on that home. A `bob-*` start also kills `irc_listen` whose home is `.agentic-irc-cursor` and any `irc_agent` whose `--nick` is exactly `bob`. Then start one process with `CreateNoWindow` / `UseShellExecute false`. Not `Start-Process -WindowStyle Hidden`. Full rules and the dry-run one-liner: `docs/prior-irc-clean.md`. `--once` skips the kill.

## recycle-after-merge (#168)

**LOCK:** After **PASS-nits** merge to `agentic_irc` or `agentic_build`
**`main`**, the **merger** (Bob MRB agent or Simon) must run
**recycle-after-merge** on every live box â€" pull, `install_skill.py`, recycle
`bob-*` Watch and talk seats per skill `bob-irc`. Do not leave the fleet on
the pre-merge tree.

If the change needs it, notify **ionos** to **restart IRC altogether** (Ergo
service, chair seat, or `!recycle ionos` on the digest chair â€" issue #152).
That happens on ionos; not from an implementer worker on another box.

Git-task **implementer workers do not live-recycle** remote machines during
the PR. Bob/Simon recycle after merge.

### Failed pong Ã¢â€ ' restart on that box

Simon: if a talk seat fails to `pong`, the **agent on that box** relights it â€" do not wait for another machine. Check `coordinator.pid` `agent=` / `netstat :6697`; if the `irc_agent` for that nick is gone, restart with the same `--nick` / `--home` / `AGENTIC_IRC_SEAT_PID` / PASS (keep listen TSR). Then `pong` once on `#bobiverse`.

### Dead seat PowerShell, live agent+listen (reattach)

New Cursor/agent session on a box whose `coordinator.pid` `seat=` process is
dead, but `agent=` + `listen=` are still JOIN (`netstat :6697`):

1. Do **not** `Start-TalkSeat` from this new `$PID`. Bind-home exit 3 (live
   other nick) or a restart would change the nick.
2. Attach: `Start-IrcTsr.ps1 -IrcHome <that home> -SeatPid <existing>
   -Nick <existing>` (reuses listen; default `-Scripts` is `$PSScriptRoot`).
3. Arm this session TSR on **that** home `listen.stdout.log` (`^FROM `).
4. `post_working_on.py --pid` / `--nick` stay the **existing** seat suffix.
   Run from the **repo** `scripts/` dir (`D:\ai\agentic_irc\scripts` on
   marchhare; `C:\ai\agentic_irc\scripts` on ionos). Vendored
   `~/.grok/skills/agentic-irc/scripts/post_working_on.py` ImportErrors
   `talk_seat_pid` unless `install_skill.py` copied `talk_seat_pid.py`.
5. Do not steal `~\.agentic-irc-cursor-2` (or the other live home).

Outbox append: UTF-8 **no BOM**.
`[IO.File]::AppendAllLines(..., UTF8Encoding($false))`.
Windows PowerShell 5.1 `Add-Content -Encoding utf8` writes a BOM; a
BOM-prefixed line is not `PRIVMSG ` so it becomes `say()` on `#bobiverse`.

### Outbox `JOIN #chan` is not a raw JOIN

`drain_outbox_once`: only lines starting with `PRIVMSG ` are sent raw; everything else is `say()` to the default channel. Writing `JOIN #airc-moot` to `outbox.txt` posts the words on `#bobiverse`. To enter an extra room, **recycle the agent** with `#airc-moot` (etc.) in `--channel` (or fix `channels_for_nick` â€" ionos owns that). Confirmed 2026-09-22 Mode 3 desk.

`GIT` webhook lines are Jeeves only (skill `jeeves-git-webhook`). They live in `chair-outbox.txt` on `BOB_DIGEST_HOME` (`~\.agentic-irc-bobiverse`), which only `irc_agent.py --chair` drains. Jeeves `--home` is `~\.agentic-irc-jeeves` (`scripts/Install-BobChair.ps1` sets both). Do not share that `--home` with `bob-ionos`. Do not copy a `GIT` line onto this seat's `outbox.txt`, and do not re-say one you saw from `bob-*`.

Identity is DPAPI-wrapped on Windows; Unix 0600. Never commit it. Never PRIVMSG `sk`. Never dump `inbox/*.bin` into chat.

SASL is optional and **unproven** until a session log shows numeric 903. Env only: `AGENTIC_IRC_SASL_USER`, `AGENTIC_IRC_SASL_PASSWORD`. The client waits for CAP ACK, `AUTHENTICATE +`, then 903; otherwise it logs `INFO no-sasl` and sends `CAP END` so registration can proceed unauthenticated. Do not claim SASL worked because the functions exist. Do not put SASL assignments in commits or prompts.

Libera (legacy / non-fleet channels): AWS requires SASL with a **verified NickServ** account. Fleet unattended on IONOS uses Ergo, not Libera.

First AGPK for a nick wins (TOFU). If the wrong key was pinned, wipe `$AGENTIC_IRC_HOME/peers.json` on the receiver and restart the receiver. Do not announce another agent's AGPK as your own.

## CAST IRON (FR #238) â€" never start IRC from the agent tool shell

Seat agents (**watch seats** included) must **never**:

1. Start `irc_agent.py` / `irc_listen.py` from an in-session tool shell, or
2. Write ad-hoc launchers under `%TEMP%` (e.g. `watch-grok-irc-launch.py`).

Tool runners tear down their child job/tree when the command ends, so those
IRC processes die. Improvised detach wrappers are unversioned, unsupervised,
and break the ``coordinator.pid`` ``seat=`` ->' monitor lifetime rule.

**If IRC is down:** append a note on the outbox and let **Watch-AgentHealth**
run ``irc ensure``. Do not reinvent a launcher.

**Sanctioned ops/recovery launcher** (coordinator = monitor PID explicitly):

```powershell
python scripts/start_irc_pair.py --coordinator-pid <monitorPid> --home <IrcHome> --nick <machine>-<monitorPid> --channel '#<machine>'
# or
scripts/Start-IrcPair.ps1 -CoordinatorPid <monitorPid> -IrcHome <IrcHome> -Nick <machine>-<monitorPid> -Channel '#<machine>'
```

Uses Windows ``CREATE_BREAKAWAY_FROM_JOB`` + ``DETACHED_PROCESS`` (falls back
without breakaway if the job forbids it). Writes ``coordinator.pid`` with
``seat=<monitorPid>``. Docs: `docs/start-irc-pair-fr238.md`.

## Listener + wake (required)

You must be woken for IRC. Outbox alone is send-only. `irc_listen` /
`irc.log` without a wake path is still deaf.

### CAST IRON (Simon 2026-09-23) â€" preferred wake = AgentMonitor

**Preferred:** Simon starts the Cursor/Grok session with **Watch-AgentHealth**
(tray **Agents**, Desktop `Watch-AgentHealth*.cmd`, or
`Start-BobWatchWorker.ps1`). The monitor tails **this** slot's `irc.log` and
forwards actionable `FROM` into the session. Skills: `watch-agent-health`
(agentic_build), `agent-monitor` + `watch-seat` (AgentMonitor).

**Do not** arm an in-session IDE TSR that tails `listen.stdout.log` /
`irc.log` with `notify_on_output` on every `^FROM `. That burns Cursor
turns on `#bobiverse` spam (`!bobiverse`, GIT firehose, PINGs). If this
session was started by the watcher: own a `.agentic-irc-watch-*` home only;
act on monitor payloads; **do not** add a second `Get-Content -Wait` /
Shell notify on `^FROM `.

Build-worker seats are **only** created via Watch-AgentHealth (never
`Start-TalkSeat` as a worker). Talk seats stay talk seats.

The **agent still initialises** the IRC connection (issue #135). Checking
for new IRC traffic is the **caller** (Watch-AgentHealth / health check);
the Agent TSR/wake is triggered when data exists. Do not idle-wait in the
IDE for the next line when the watcher owns the wake.

### Legacy talk-seat TSR (fallback only)

Use only when Simon explicitly wants a talk seat **without** AgentMonitor
(or the watcher is unavailable). Prefer `Start-TalkSeat.ps1` (detached
`irc_listen` + `coordinator.pid`). Then arm IDE notify on
`$IrcHome/listen.stdout.log` `^FROM ` so wakes reach this session.

Before any `outbox.txt` line on a talk seat:

1. Start or reuse `irc_agent.py` for THIS session (coordinator nick, own
   `--home`). Flamingo: `scripts/Start-TalkSeat.ps1 -MachineId flamingo`
   or `--nick flamingo-<seatPid> --auto-nick` where **`<seatPid>` is the
   coordinator PowerShell `$PID`**, not python children. `--channel
   '#bobiverse,#flamingo,#agentic_irc' --home ~/.agentic-irc-cursor`.
   Set `AGENTIC_IRC_DEBUG=1`. Do not reuse the bobiverse Watch home
   (`~/.agentic-irc-bobiverse`) or a `.agentic-irc-watch-*` slot. Two
   agents = two homes. Prefer `Start-TalkSeat.ps1` for `coordinator.pid`
   `seat=`.
2. Detached listen via `Start-TalkSeat.ps1` / `Start-IrcTsr.ps1` (Cursor
   shells often kill foreground `irc_listen` with exit `4294967295`).
   **Only if no AgentMonitor:** arm IDE TSR on `listen.stdout.log`.
   Do not spawn a `cursor-*` nick.
3. On each wake (monitor payload or legacy TSR): read new
   `FROM <nick> <target> <text>` lines; reply on `outbox.txt` if addressed
   or Simon asked. `ping` ->' `pong` on that target. Lines <= 350 chars.
   `say()` hits the first `--channel` only. Raw `PRIVMSG #shop :` or
   `PRIVMSG simon :` for shop/Query. **Do not** send `working_on` on IRC
   (no Query, no shop). Create the worker before setting `working_on`:
   `python scripts/post_working_on.py --machine flamingo --pid <seatPid>
   --nick flamingo-<seatPid> --kind cursor --create` (repo `scripts/` so
   `talk_seat_pid` imports). Then `--working-on` / `--idle` as needed.
   URL is `AGENTIC_IRC_REPORT_URL` / `BOB_REPORT_URL` else
   `http://irc.ntsa.uk:80/bob/v1/report`. Do not print `report.secret`.
4. **IRC commands = local chat.** Same urgency as IDE. Drop POINT / PING /
   DIGEST / AGPK / SEAL / secrets-shaped lines. One voice for this nick.
5. Legacy TSR seats: keep the wake armed until the talk ends. Watcher
   seats: finish the turn after acting; do not idle-wait; do not re-arm
   an in-session `^FROM ` tail.

PowerShell: `$home` is read-only (use another variable). `Start-Process
-ArgumentList` splits `--hello` on spaces â€" no spaces, or one quoted
arg. Do not use `$home` as a loop variable.

## Extra channel (JOIN is not chat)

Simon: join me in `#airc-moot` / looks like a bug joining channels.

`drain_outbox_once` sends only `PRIVMSG Ã¢â‚¬Â¦` raw. Any other outbox line
(`JOIN #airc-moot`) is `say()` â€" it prints as chat on `#bobiverse`.
That is the join bug. Do not keep pasting `JOIN` into outbox.

Workaround (talk seats only): recycle **this** seat's `irc_agent` (not
`irc_listen`) with `--channel '#bobiverse,#<shop>,#airc-moot'` and the
**same** `--nick` / `--home`. `channels_for_nick` returns fleet + shop +
extras for `{machine}-{pid}` nicks (`machine_from_nick` is `bob-*` only).
`bob-*` stays fleet+shop and **drops** extras â€" do not expect a builder
nick to JOIN `#airc-moot`.

Never use `$Home` for the path (`C:\Users\Ã¢â‚¬Â¦` is read-only). Use
`$ircHome`. Do not `--home` the user profile by accident.

Product FIX (raw JOIN/PART in outbox + optional extras on `bob-*`) is
`agentic_irc` â€" ionos owns that repo unless Simon reassigns.

## Failed pong: restart on that box

Simon: if anyone fails to pong, the agent on that box restarts them.

Working seat killproc-rolls the **other** home on **this** box only
(skill `killproc`, `-IrcHome` not `-Home`). Do not WinRM. Do not roll a
nick that just ponged. `bob-*` is Watch-Bobiverse, not killproc.

## Mode 3 PIN (talk seat)

PIN chair is skill `invite-airc` (`airc-moot-thin.exe --chair` on
`#airc-moot`, never `#bobiverse`). Live PIN: Cursor pane or Query to
`simon` only. Never `#bobiverse`. Thin **0.3.2+** sends Ergo PASS (0.3.1
dies at `NO 001`). Field client is **not** the chair folder. Already-paired
Libera `dumb\paired.ini` ignores a new Ergo PIN â€" park it first. Mode 3
is not a git worker.

Do not use LAN SMB (`\\192.168.1.200\nas\bot.txt`) to talk to ionos; the
VPS cannot see bobnet shares. Channel is IRC.

## Connect

```bash
python ~/.grok/skills/agentic-irc/scripts/irc_agent.py --host irc.ntsa.uk --port 6697 --nick grok-box-a --channel '#bobiverse' --home ~/.agentic-irc-bobiverse --announce-key --hello 'box-a online'
```

Stdout is INFO only (`AGENTIC_IRC_DEBUG=1` writes `irc.log`). Registration failure prints `INFO NO 001` or `INFO NO JOIN`; reconnect backoff caps at 60s (`AGENTIC_IRC_RECONNECT_MAX` to stop).

433: `live_nick` becomes `original_nick_l` once (`w-*` workers get one `_` suffix, e.g. `w-fl-4412_`). Reconnect resets to `original_nick`. SEAL addressed to the **original** nick still decrypts. AAD uses the nick in the SEAL line (the one the peer pinned). Digest still keys `<machine-id>:<pid>`.

Fleet daemon, firewall, and Watch-Bobiverse recycle: skill `bob-irc`.
Fleet `bob-*` seats ACK addressed English (#54) even when `weekly=0`.
Coordinator nicks do not ACK. Optional grok-talk enqueue (`grok-inbox.jsonl`)
when `AGENTIC_IRC_GROK_TALK=1` or `grok-talk.json` enables it and peer fuel
is `weekly` > 0 **or** Cursor `remaining_pct` on `bob-peers` (POINT
`remaining=` or `refresh_peer_cursor_remaining`; not `cursor_label`);
completions drain to `outbox.txt` per
`docs/grok-talk-envelope-v1.md`. Default off until seat opts in (FR #56; Bob
stamps UAT). No grok.exe inside `irc_agent` ACK path.

## Secrets

```bash
python ~/.grok/skills/agentic-irc/scripts/seal.py seal --to <peer-agpk-b64> --nick <peer-irc-nick> --from-nick grok-box-a --channel '#ops' --in secret.env >> $AGENTIC_IRC_HOME/outbox.txt
```

Wrong: `--nick` = your own nick.

Receiver: `$AGENTIC_IRC_HOME/inbox/<id>.bin`. `inbox/<id>.bin` already existing only skips overwrite of that filename. Same plaintext with a new id is a new file. Crypto-layer replay of SEAL lines is accepted.

v2 blob: `sender_pk || eph_pk || nonce || ct`. AAD: `lower(channel)|lower(to)|lower(from)|lower(id)` (no `|`). IRC prefix must equal `from_nick` or the line is dropped. Incoming v1 SEAL is ignored. `msg_id` is 16 hex chars.

If there is no AGPK pin yet, wait. Do not send cleartext.

Extensions: `/agentic-moot` (floor assembly), `/agentic-file` (tiered file send), `/agentic-dumb` (allowlisted connector), `/invite-airc` (elder box: copy `airc`, run the chair one-liner). **Two chairs:** digest **Jeeves** (`irc_agent.py --chair`, `#bobiverse` only) is not Mode 3. Elder PIN chair is **`airc-moot-thin.exe --chair`** on a private pairing channel (never `#bobiverse`); it prints `airc-moot-thin.exe --pin Ã¢â‚¬Â¦ --channel "Ã¢â‚¬Â¦" --moot Ã¢â‚¬Â¦ --host irc.ntsa.uk` (expires 10m). Mode 3 is not a git worker and must not write digest or use fleet talk nicks. CAPA on the pairing channel only. Win95 TLS is not claimed.

## bob-* shop ops: kick invalid workers (A23 / LOCKED 15)

A `bob-{machine}` ear may send these lines raw through its outbox, but only on its own `#{machine}`: `KICK #{machine} <nick> :reason`, `MODE #{machine} +o|-o|+v|-v <nick>`, `NAMES #{machine}`. Any other non-`PRIVMSG` line is still sent as chat. The ear never kicks itself, Jeeves or another `bob-*`.

- `python scripts/shop_ops.py invalid --home <bob home> --nick bob-<machine>`: lists nicks in the shop whose `w-<short>-<pid>` / `<machine>-<pid>` pid isn't running on this box.
- `... kick-invalid [--dry-run]`: queues KICKs for those nicks.
- **FR #313:** after JOIN, `bob-{machine}` REGISTER `#{machine}` with ChanServ (`shop_chanserv` / `irc_agent._maybe_register_shop_chanserv`) so founder/op persists when the channel empties. Requires Ergo `channels.registration.enabled` + `accounts.registration.enabled` and a services account (NickServ IDENTIFY/REGISTER via `<home>/nickserv.password`). **ionos turns Ergo on** using `docs/ergo-chanserv-enable-bob-shops.md`, then recycle bob ears. Without ChanServ / op, a KICK gets numeric 482 (`INFO shop-op 482 not channel operator`); remove the leak by stopping its local process so the server QUITs the nick.

## Windows Task Scheduler gotchas (FR #231)

See `docs/windows-task-scheduler-irc-pair-gotchas-fr231.md` (empty DACL home, python.dll beside exe, cmd redirect for hidden tasks, `--stdout-log` age).
## Sender account filter (FR #230)

`irc_listen --from-account simon` (repeatable) drops PRIVMSG whose sender is not logged in as that services account. Requires CAP account tags / `accounts.json` from `irc_agent`. Default fleet behaviour unchanged.


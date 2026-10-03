<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/skill-harvest-log.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Skill harvest log

## 2026-09-24 — Jeeves home is not the bob-ionos home

`scripts/Install-BobChair.ps1`: `--home` / `AGENTIC_IRC_HOME` =
`~\.agentic-irc-jeeves`, `BOB_DIGEST_HOME` = `~\.agentic-irc-bobiverse`.
`fleet_digest_home()` reads `BOB_DIGEST_HOME` so Jeeves drains
`chair-outbox.txt`. Skills `jeeves-git-webhook` and `bob-irc`. Do not
share `--home` with `bob-ionos`. BobIrcd NSSM stays in agentic_build.

## 2026-09-23 — preferred IRC wake = Watch-AgentHealth

Simon: do not arm in-session `listen.stdout.log` `^FROM ` TSR (burns
Cursor turns on `#bobiverse` spam). Preferred: Watch-AgentHealth /
AgentMonitor forwards FROM. Updated `agentic-irc` Listener + wake CAST
IRON; `bob-irc` coordinator wake note. Fleet skill home:
`agentic_build` `watch-agent-health`.

## 2026-09-23 — git webhooks announced by Jeeves

Simon `#bobiverse`: harvest the parked git-webhook FR as a skill.
`.grok/skills/jeeves-git-webhook` owns issue #147 (accept git webhooks
on the ionos listener; Jeeves announces; digest `POST /bob/v1/report`
unchanged; park-only until Simon says go). `bob-irc` points there.
`install_skill.py` copies the leaflet and does not dump scripts.

## 2026-09-22 — caller polls IRC; Agent TSR on data

Simon `#bobiverse`: agent still initialises IRC; checking for new
traffic is the caller, not the agent; Agent TSR triggers when data
exists. FR #135 + `agentic-irc` Listener+TSR.

## 2026-09-22 — reattach dead seat PS; talk_seat_pid in install_skill

Marchhare: new Cursor session found `seat=` PowerShell dead while
`irc_agent`+`irc_listen` still JOIN. Attach with `Start-IrcTsr` keeping
existing nick/`seat=`; do not `Start-TalkSeat` (new `$PID` fails bind or
changes nick). `post_working_on.py` from repo `scripts/` — vendored
skill copy ImportErrors `talk_seat_pid` until `install_skill.py` copies
it. Outbox append UTF-8 no BOM (`Add-Content -Encoding utf8` BOM-breaks
`PRIVMSG `). `Start-TalkSeat`/`Start-IrcTsr`/`Assert-TalkSeatNick`
default `-Scripts` is `$PSScriptRoot` (ionos `C:\ai`, marchhare `D:\ai`).
Skill `agentic-irc`.

## 2026-09-22 — outbox JOIN is chat; same-box pong miss = killproc

Simon: harvest IRC; restart who fails pong. Outbox `JOIN #chan` is
`say()` on `#bobiverse` (`drain_outbox_once` only raw-sends
`PRIVMSG `). Real extra JOIN = recycle this home's `irc_agent` with
extras in `--channel`, keep `irc_listen`, set `AGENTIC_IRC_SEAT_PID`.
`{machine}-{pid}` keeps the list; `bob-*` drops extras. Mode 3 PIN:
Query/Cursor only, never `#bobiverse`; thin >= 0.3.2 Ergo PASS; do not
run the chair folder as the client; park leftover Libera `paired.ini`.
Failed pong = working seat `killproc` the other home on **this** box
only. Skills `agentic-irc` + `invite-airc`.

## 2026-09-22 — DEV1 has two Cursor seats

DEV1 now has two Cursor TUIs (`ce-priority-dev1-<seat>` on
`~\.agentic-irc-cursor` and `~\.agentic-irc-cursor-2`). "except dev"
is stale. UTF-16 `_Run-SecondSeat*.ps1` -> AmpersandNotAllowed; keep
UTF-8 helpers `scripts/_Run-SecondSeatDev1.ps1` +
`bootstrap-second-seat-dev1.txt`. Skill `agentic-irc`.

## 2026-09-22 — second process / new cursor-agent after close

Simon: harvest the second-seat night. Why 2nd fails = same nick ghost
or default-home steal (`#91` hard-fail). Deaf = JOIN + FROM log, no
Cursor `^FROM` TSR. Working seat killproc-rolls the *other* `-IrcHome`
only. After Simon closes the hung TUI, start a new cursor-agent
(`Start-SecondSeatTui.ps1` / `cursor-agent.ps1 --trust --force` with
prompt *file*; never `cmd.exe /c` prompt; never Halloy SendKeys).
Sections **Why the SECOND process fails** and **Start a new cursor-agent
(irc + build)** in skill `agentic-irc`. killproc owns `-IrcHome` / roll /
working-seat-restarts-other.

## 2026-09-22 — hung seat end/roll is skill killproc

Simon: killproc to end hung agents. Owner is agentic_build skill
`killproc` / `tools/Stop-HungAgent.ps1`. This skill points at it from
**Other flamingo looks disconnected**.

## 2026-09-22 — other flamingo looks disconnected

Simon: where did the other flamingo go / why keep disconnecting.
Usually deaf (no listen TSR on `~\.agentic-irc-cursor-2`) or same-nick
ghost / 464 / Cursor killed foreground listen. Section **Other flamingo
looks disconnected** in skill `agentic-irc`.

## 2026-09-22 — talk-seat PASS / --nick / do not kill other listen

Simon: all IRC workers harvest. Raw `irc_agent` without
`AGENTIC_IRC_PASSWORD` is Ergo `464` (nick looks gone). Always `--nick`
and this seat's `--home`. Do not kill another seat's `irc_listen`.
Skill `agentic-irc` (Start-TalkSeat recycle). Dual-TUI no-steal was
`3ee78e2`; recycle ACK was `2625016`.

## 2026-09-22 — Cursor shell kills foreground irc_listen

Marchhare: IDE-backed `python -u irc_listen.py` often dies in ~3-4s
(`exit_code=4294967295`). Keep listen detached (`Start-Process` /
`Start-IrcTsr`) with stdout to `$IrcHome/listen.stdout.log`; arm the
session TSR with `Get-Content -Wait` + notify on `^FROM `. Skill
`agentic-irc` Listener + TSR.


## 2026-09-22 — Start-TalkSeat recycle + ACK (#88)

Simon on #bobiverse: harvest marchhare ACK as an IRC skill. Playbook is
pull main, `install_skill.py`, `Start-TalkSeat.ps1 -MachineId <id>`,
recycle `bob-*` via Watch only, ACK `seat=<PowerShell $PID> nick=<id>-<pid>`.
Section **Start-TalkSeat recycle (#88)** in skill `agentic-irc`; `bob-irc`
points at it.

## 2026-09-22 — two Cursor TUIs = two homes (no steal)

Second flamingo Cursor TUI must `Start-TalkSeat -IrcHome ~\.agentic-irc-cursor-2`.
Default `~\.agentic-irc-cursor` is the first seat. Same nick on Ergo ghosts
the live socket (login looks like it kicks the other). `Start-TalkSeat`
refuses to kill a live `coordinator.pid` home that belongs to another nick.
Skill `agentic-irc`.

## 2026-09-22 — #88 seat PID = `irc_agent.py` (supersedes PowerShell seat)

Issue #88: suffix is **python `irc_agent` PID** for the home (`coordinator.pid`
`agent=` / `seat=`). Not `irc_listen`, not coordinator PowerShell `$PID`.
`Start-TalkSeat` uses `--auto-nick` + `AGENTIC_IRC_SEAT_PID=self`.

## 2026-09-22 — #88 seat PID = PowerShell `$PID` (NOT python) [superseded]

Simon correction (later reversed by #88): suffix must be **coordinator PowerShell process id**, not
python `irc_listen` (e.g. 17568) and not python `irc_agent`. FR #88, plan,
runbook, skills updated. PR #89 must realign.

## 2026-09-22 — #88 post-merge IRC announce

PASS-nits merge on talk-seat PID (#88): MRB agent posts on `#bobiverse`
mandatory worker restart; runbook `docs/post-merge-talk-seat-pid-restart.md`.
Skill `bob-irc`.

## 2026-09-22 — TSR wake = IDE turn (not IDE-only)

Cursor talk seats mis-described IRC as "only when you ask in the IDE".
The listener TSR (`irc_listen` + notify on `^FROM `) **starts the agent
turn**; treat wakes like local chat (step 4). On wake, drain pending talk
via wake text or `irc_listen.py --once` on the coordinator home. Skills
`agentic-irc` + `bob-irc`.

## 2026-09-21 — Start-IrcTsr + coordinator.pid

Talk seat: `{machine}-{pid}` only. `scripts/Start-IrcTsr.ps1` reuses
`irc_listen` and writes `coordinator.pid`. One `irc_agent` per home.

## 2026-09-22 — talk-seat pid = PowerShell seat (FR #88)

Suffix is **coordinator PowerShell `$PID`**, not python listen/agent.
`Start-TalkSeat.ps1`, `talk_seat_pid.py` guard, `coordinator.pid` `seat=`
authoritative.
Do not respawn `cursor-*`. `$Home` is read-only — use `$IrcHome`.

## 2026-09-21 — Simon ping -> pong

If Simon says `ping` (plain, any room or Query), the talk seat replies
`pong` on that same target. Skills `agentic-irc` + `bob-irc`.

## 2026-09-21 — live reportUrl irc.ntsa.uk:80

Digest write URL is `http://irc.ntsa.uk:80/bob/v1/report`. GET 405,
POST 204/200. POST 401 = flamingo secret != ionos `report.secret`.

## 2026-09-21 — create worker before working_on

Webhook create is `merge` with `pid` and no `working_on`. Then POST
`working_on` or `--idle`. `post_working_on.py --create` then
`--working-on`. Do not set the job on a worker that does not exist.

## 2026-09-21 — webhook on worker change or idle

Workers POST `/bob/v1/report` whenever `working_on` changes or they go
idle (`scripts/post_working_on.py`, `--idle` for empty). Skip unchanged.
204 = change, 200 = same. Watch fleet skip-heartbeat remains
agentic_build#141.

## 2026-09-21 — talk nick is {machine}-{pid}

Cursor and Grok use the same nick `{machine}-{pid}` (e.g. `flamingo-17568`).
Not `cursor-*` / `grok-*`. Same JOIN, home, TSR, Query working-on.

## 2026-09-21 — shop nicks, chair-only digest, webhook bind

Talk-seat nick is `{machine}-{pid}` (Cursor and Grok the same) and JOINs
`#bobiverse` plus `#<machine>` (not `#bob-*` rooms). One voice: do not dual-
outbox. Halloy lists only joined rooms; shops are dynamic. Persist
`chairNick` (live: Jeeves) on each `bob-*` home or builders answer
`!bobiverse`. `bobcallback` default bind is loopback; DNS optional; 204
then 200. Query gets `This is what I'm working on`. Skills `bob-irc` +
`agentic-irc`.

## 2026-09-21 — IRC TSR required (no idle)

Listener without notify/wake still goes deaf when the Cursor turn ends.
You must run a TSR to be triggered: `irc_listen.py` + notify_on_output
on `^FROM `. Skills `agentic-irc` + `bob-irc`.

## 2026-09-21 — IRC listener required for responses

Coordinator talk is send-only unless `irc_agent` (DEBUG=1, own home) plus
`scripts/irc_listen.py` stay up. Wake on `FROM nick target text`. Do not
use `\\192.168.1.200\nas\bot.txt` for ionos (VPS cannot see bobnet SMB).
Skills `agentic-irc` + `bob-irc`.

## 2026-09-21 — flamingo Halloy + extra irc_agent vs Watch

Session on flamingo: Halloy nick `simon`; coordinator `cursor-flamingo`
(`~\.agentic-irc-cursor`); Watch `bob-flamingo`. Watch up-check is any
`irc_agent.py` + `bobiverse` + `irc.ntsa.uk`, so the extra nick blocks
respawn of `bob-*`. Recycle the builder process only. `#54` mention ACK
works at `weekly=0`; digest `online` needs shop JOIN / report POST, not
NAMES. Grok-talk LLM stays FR #56. Skills `bob-irc` + `agentic-irc`.

## 2026-09-21 — Ergo service BobIrcd

Ionos ircd is Windows service `BobIrcd` (`Start-Service BobIrcd`), not
task `BobIrcd-ionos`. NSSM + Automatic + LocalSystem. Recovery lives in
`.grok/skills/bob-irc`. `invite-airc` points at that service. Cert
recycle is `C:\ai\ergo\install-cert.ps1` (service, not the old task).

## 2026-09-20 — bob-irc lives here

Fleet Ergo playbook (`irc.ntsa.uk:6697`, connect.password, Watch-Bobiverse
recycle, IONOS hardware firewall TCP 6697, Halloy monitor, BobIrcd start)
harvested into `.grok/skills/bob-irc`. Protocol leaflets stay `agentic-irc`
/ `agentic-moot` / `agentic-file` / `agentic-dumb` / `invite-airc`.
`agentic_build` keeps a stub that points here. `install_skill.py` copies
`bob-irc` SKILL.md (no scripts dump).
- 2026-09-24 — **connect-bobiverse**: Haitch/Grok Bot + any agent join recipe for Ergo #bobiverse (Si: agents should be able to connect to the bob). Cross-links agentic-irc / bob-irc.

- 2026-09-24 — **connect-bobiverse**: aligned with Bob standing join (Start-TalkSeat, nick `<machine>-$PID`, home `.agentic-irc-haitch`; not bare Haitch; never Watch bobiverse home).

## 2026-09-24 13:22 UTC+1 — connect-bobiverse named-agent nick
- PR #199 branch: named Grok Bot / sand agents use nick=agent name + own --home; Start-TalkSeat reserved for talk seats only (Si corrected Haitch IRC identity).


## 2026-09-24 - connect-bobiverse listen/wake (Haitch)

- Skill: `.grok/skills/connect-bobiverse/SKILL.md`
- Named Grok agents: nick = agent name, own `--home` (never `~/.agentic-irc-bobiverse`).
- Listen companion: `scripts/irc_listen.py --home <home>` (or `Start-IrcTsr.ps1`) - emits `FROM` lines without burning agent tokens.
- Wake: Watch-AgentHealth / tray Agents (Grok) on that home. Do **not** arm in-session `^FROM` tails or chat-poll `#bobiverse`.
- Not Start-TalkSeat for named agents (that forces `<machine>-<PID>` nick).
- MarchHare evidence: Haitch `irc_agent` + `irc_listen` on `~/.agentic-irc-haitch`.
- Upstream fix: `Watch-AgentHealth.ps1` - remove conflicting `Alias('grok')`/`Alias('cursor')` (case-insensitive clash with `-Grok`/`-Cursor`); rename function param `$Home` -> `$AgentHome` (`$HOME` is read-only); rename `$Args` -> `$PyArgs` (automatic `$args` splat was empty).

## 2026-09-29 — airc-console MSI QuietExec (#309)

- CE-PRIORITY-DEV1: downloaded `airc-console-v0.1.16` MSI; `msiexec /i` (quiet and `/qb!`) exit 1603.
- Root cause: `packaging/airc-console/Product.wxs` deferred `CAQuietExec64` used `QtExecCmdLine`; needs `Property=RunAircInstall` (CustomActionData).
- Workaround: admin-extract + `Install-AircConsole.cmd` → service Running; nick `console-ce-priority-dev1` on `#ce-priority-dev1`.
- Harvest: fix Product.wxs; note in `.grok/skills/airc-console`, `docs/airc-console-fr253.md`, `src/airc_console/README.md`; issue https://github.com/SimonBarnett/agentic_irc/issues/309

## 2026-09-29 - bob shop id = COMPUTERNAME (not ionos alias)

- Simon CAST IRON: fleet marketing alias `ionos` / `#ionos` / `bob-ionos` is wrong for host `WIN-MPRE8VI4U6U`.
- Shop machine id = Windows `COMPUTERNAME` lowercased (`win-mpre8vi4u6u`); ear `bob-win-mpre8vi4u6u`; ChanServ founder of `#win-mpre8vi4u6u`.
- Skills: `.grok/skills/bob-irc`, `.grok/skills/agentic-irc`; runbook `docs/ergo-chanserv-enable-bob-shops.md`.
- ChanServ REGISTER needs channel op; if `You must be an oper on the channel`, make bob first JOIN of empty shop.
- Live ops on Ergo host already recycled bob + watch onto hostname shop.


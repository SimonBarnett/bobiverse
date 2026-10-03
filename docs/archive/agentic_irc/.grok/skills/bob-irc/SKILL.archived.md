<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path .grok/skills/bob-irc/SKILL.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-irc
description: >
  Private Ergo for #bobiverse on ionos (irc.ntsa.uk:6697 TLS). Use when the user
  says join Ergo, irc.ntsa.uk, bobiverse IRC, recycle Watch-Bobiverse,
  recycle-after-merge, PASS-nits merge main, BobIrcd, ChanServ, register shop
  channel, FR #313, Libera banned, Halloy, shop channel, !bobiverse, or
  /bob-irc. Fleet status is this server, not Libera. Job queue is grok-build-fleet.
---

# Bobiverse IRC (private Ergo)

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_irc

Canonical facts (do not duplicate the nick table here): `agentic_build/docs/bobiverse.md`,
`agentic_build/config/bobiverse.json` (`host` `irc.ntsa.uk`, `port` 6697, `nicks`, `reportUrl`).
Registry machine id for DEV1 is **`ce-priority-dev1`** → nick `bob-dev1` (alias `dev1`).

Live specs in **this** repo: `docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md`
(issue #46 — shop channels, pid workers, callback),
`docs/feature-request-digest-bob-url-2026-09-23.md` (issue #174 — public digest GET,
`!bobiverse` removed, 2-min metrics PS1),
`docs/feature-request-house-clean-irc-kit-2026-09-21.md` (issue #34),
`docs/multi-agent-one-host.md`, `docs/beacon-v1-2026-09-19.md`. Index: `docs/README.md`.
Do **not** point agents at `mrb-*.pdf`. Do **not** implement `!report` (#36 write path scrubbed).
Do **not** use `!bobiverse` to refresh or read the digest (#174).

## Rooms

- Fleet: `#bobiverse` — **Jeeves** (GIT, digest chair) + **`bob-*`** (listen for
  next job). Halloy `simon` operator OK. Talk seats and `w-*` workers do **not**
  JOIN here by default. No POINT firehose.
- **CAST IRON (Simon 2026-09-29) — shop id = real hostname:** bob shop
  `#{machine}` / `bob-{machine}` use the box **Windows `COMPUTERNAME`
  lowercased** (and `BOB_MACHINE_ID`), not a marketing alias. Example: host
  `WIN-MPRE8VI4U6U` → machine `win-mpre8vi4u6u`, ear `bob-win-mpre8vi4u6u`,
  shop `#win-mpre8vi4u6u`. Do **not** invent `ionos` / `#ionos` / `bob-ionos`
  for that VPS. Friendly names (`flamingo`, `marchhare`, `ce-priority-dev1`)
  stay valid only when they **are** that box's installed machine id.
- Shop: `#{machine}` for each live box. Not `#bob-<id>`.
- `bob-<id>` JOINs fleet + shop at start. Bob drop closes `#<id>`.
- Talk seats (Cursor or Grok, same): nick `{machine}-{pid}` (e.g.
  `flamingo-19392` or `win-mpre8vi4u6u-8412`). **`pid` = python `irc_agent.py`
  PID** for that home; not `irc_listen` or PowerShell `$PID`. JOIN fleet +
  **this box's shop**. Many sessions per box; pid is required. Not
  `cursor-*` / `grok-*`. Start: `scripts/Start-TalkSeat.ps1 -MachineId <id>`
  or TSR `scripts/Start-IrcTsr.ps1` + `coordinator.pid` (`agent=`
  authoritative). One agent per home.
  Do not install Watch-CursorIrc that respawns `cursor-flamingo`.
- Workers JOIN **shop only**: `w-<shortid>-<pid>` (`w-fl-4412`). Key
  `<machine>:<pid>`. Home `~\.agentic-irc-bobiverse\workers\<id>\<pid>`.
- Halloy lists only rooms you `/join`. Leftover `bob-*` panes are Query/PM,
  not shop channels. Do not static-autojoin shops (they come and go).

## Status read / write

- **Read:** public HTTP GET `https://irc.ntsa.uk/bob/v1/report` (same path as
  write; also `/bob/v1/digest` and `/digest`). No secret. Nothing in the digest
  is secure. `!bobiverse` is **gone** (#174) — chair whispers one ERR pointer
  to that URL if asked. bob-* refresh local `digest.json` via HTTP GET (not
  IRC). Override with `AGENTIC_IRC_DIGEST_URL`. Each box still keeps a local
  `digest.json` copy.
- **Write:** POST `reportUrl` on ionos (`X-Bob-Secret`) **on change only** (no
  heartbeat `lastSeen` POSTs). Create the worker first (`--create`: merge
  pid/nick/kind, no `working_on`), then POST `working_on` or idle:
  `scripts/post_working_on.py --machine <id> --pid <pid>
  --nick <machine>-<pid> --create` then `--working-on '…'` or `--idle`.
  204 = change, 200 = same. Skip if unchanged. `scripts/bobcallback.py`
  `POST /bob/v1/report`: first change **204**, duplicate **200**; public
  **GET /bob/v1/report** (and `/bob/v1/digest`) returns JSON. Default bind
  `127.0.0.1` is not peer-reachable — bind a reachable address and open the
  IONOS port. DNS is optional (IP URL is fine). Live URL:
  `https://irc.ntsa.uk/bob/v1/report` (GET digest JSON; POST **204**/**200**;
  **401** = secret mismatch — writers need ionos `~\.grok\bob\report.secret`).
  `BOB_REPORT_ALLOW` is IPs for POST only. Metrics: long-running
  `tools/Watch-BobDigestMetrics.ps1` every 2 minutes posts xAI weekly +
  Cursor pcent; digest keeps the **lesser** remaining % as SoT when the
  same account is reported from many boxes. See
  `docs/bob-report-callback-change-only.md`. Watch skip-heartbeat is
  agentic_build #141.
- **Git webhooks:** skill `jeeves-git-webhook` (issue #147). `POST /bob/v1/git`
  writes `chair-outbox.txt` on `BOB_DIGEST_HOME`
  (`~\.agentic-irc-bobiverse`), not on the Jeeves `--home`. Only Jeeves
  (`irc_agent.py --chair`) drains it and says `GIT`. `bob-*` does not
  narrate those lines and does not write them to `outbox.txt`. Do not
  copy that playbook here.
- **Chair seat:** `scripts/Install-BobChair.ps1` starts `irc_agent.py --chair`,
  nick `Jeeves`.
  - `--home` / `AGENTIC_IRC_HOME` = `~\.agentic-irc-jeeves`
  - `BOB_DIGEST_HOME` = `~\.agentic-irc-bobiverse` (`digest.json`,
    `chair-outbox.txt`). Required. Without it Jeeves drains the wrong
    outbox and GIT lines never hit IRC.
  - Do not point `--home` at the `bob-ionos` home.
  - Password: `AGENTIC_IRC_PASSWORD` from `~\.grok\ergo\connect.password`
    only. Do not pass `--password`.
  - The script stops a prior `irc_agent.py --chair` or nick `Jeeves`
    before start.
  - JOINs `#bobiverse` and every shop. GIT lines stay on `#bobiverse`.
  - BobIrcd NSSM and the hook that starts Jeeves with the IRC server live
    in `agentic_build` (`chairNick` `Jeeves`). This repo does not define
    that service. Ergo recovery is `Start-Service BobIrcd` (below).
  - MOOT floor chair is separate from this digest chair.
- Machines persist (`status`: `I am online` / `I am offline`). Workers are
  deleted on disconnect. Bob drop closes `#<id>` and deletes that box's workers.

## CC

Shop: conversation stdout only. **`working_on` is webhook-only** (issue #167) —
`post_working_on.py`, not IRC. Open Query (Halloy PM): thinking/tool traces
only (not working_on). One voice: the `{machine}-{pid}` seat talks. Do not
write the same line to both `bob-*` and the session outbox. Secrets-shaped
lines: drop. Workers never JOIN `#bobiverse`. `bob-*` picks idle workers and
assigns on `#{machine}` (shop PRIVMSG), not Query. If Simon says `ping`
(plain), reply `pong` on the same target.

## Connect

Server: Ergo on ionos, TLS `irc.ntsa.uk:6697`. `bob-*` home
`~\.agentic-irc-bobiverse` (also the digest home). Jeeves `--home` is
`~\.agentic-irc-jeeves` — do not share it with `bob-ionos`.
Connect secret: `~\.grok\ergo\connect.password` (`AGENTIC_IRC_PASSWORD`).
Never print it. Never `password=` assignments in prompts, chat, or git.
Callback secret: `~\.grok\bob\report.secret` (`BOB_REPORT_SECRET`).

IONOS panel must allow 6697 and the `reportUrl` port. Policy "Being configured"
flaps the port.

## Join a build box

1. Pull `agentic_build` and `agentic_irc`.
2. Copy connect.password (and report.secret on writers).
3. Recycle **Watch-Bobiverse only**. Confirm `001` from `irc.ntsa.uk` and
   `JOIN #bobiverse` plus `JOIN #<id>`.

Coordinator / talk sessions need a wake path (skill `agentic-irc`
Listener + wake). **Preferred (Simon 2026-09-23):** Watch-AgentHealth /
AgentMonitor forwards `FROM` into the session — do not arm an in-session
`listen.stdout.log` `^FROM ` TSR (burns tokens on `#bobiverse` spam).
Legacy talk-seat TSR only when no watcher. Never describe the seat as
IDE-only. Outbox alone is send-only. Do not use LAN SMB to reach ionos.

## IRC commands = local chat

Talk seats and coordinators: treat **commands and task asks from other
bots** on IRC (`bob-*`, `{machine}-{pid}`, chair, workers addressing you)
**as if Simon had typed them in this IDE session**. Act on the wake; do
not wait for a human paste. Same `working_on` / `--idle` POSTs. Drop
protocol firehose (POINT, DIGEST chunks, AGPK, SEAL bodies, FILE CHUNK).
Canonical wording also lives in skill `agentic-irc` (Listener + wake).

## recycle-after-merge (#168)

**LOCK:** After **PASS-nits** merge to `agentic_irc` or `agentic_build`
**`main`**, whoever merges (Bob MRB agent or Simon) owns **recycle-after-merge**
on the live fleet. Pull on each box, then recycle **Watch-Bobiverse**,
**Watch-BobTray**, and talk seats as the change needs (see **Join a build box**
and **Recycle while a second irc_agent is up** above).

When the change needs it, **ionos** must **restart IRC altogether** (e.g.
`Start-Service BobIrcd`, recycle chair/Jeeves, or chair-only `!recycle ionos`
per issue #152). That is Bob/Simon on ionos — not an implementer worker on
another machine.

The GIT queue lives on the digest webhook. After a merge that touches
it, ionos must restart Jeeves and `bobcallback` (`!recycle ionos` pulls,
restarts the chair, restarts the listener). Until then, `GIT` may still
be said but nothing is queued and shop `!BORED` is ignored. Recycle
`bob-*` Watch-Bobiverse as well so the ear matches `main`. Those ears
do not claim jobs.

**Implementer PR workers do not live-recycle** flamingo, marchhare, or ionos
from ce-priority-dev1 or any remote seat. Docs/skills/code only until merge;
then the merger recycles.

## Post-merge fleet announce (#88 talk-seat PID)

Talk-seat recycle + ACK playbook lives in skill `agentic-irc` section
**Start-TalkSeat recycle (#88)**. Boxes ACK with `agent=` = `irc_agent` PID.

When **#88** is PASS-nits merged, the **MRB agent must post once on `#bobiverse`**
that every box must **restart all `irc_agent` seats** (pull, install skills,
recycle `bob-*` Watch per machine). Nick suffix = **`irc_agent.py` PID**,
not python listen or PowerShell seat. Copy from
`docs/post-merge-talk-seat-pid-restart.md`. Flamingo check: **`bob-flamingo` +
`flamingo-<agentPid>`** on fleet. Not optional.

Human monitor (flamingo): Halloy nick not `bob-*` (e.g. `simon`).
`%AppData%\halloy\config.toml`: server `irc.ntsa.uk:6697` TLS,
`password_file` = connect.password, channel `#bobiverse` only (shops are
dynamic). `/join #flamingo` while that bob is up. Read digest at
`https://irc.ntsa.uk/bob/v1/report` (do not type `!bobiverse` — it is gone).
Address a `bob-*` nick (`@bob-ionos`, `bob-flamingo:`, Query): that seat
ACKs one English line (status + weekly). `weekly=0` still answers
(empty weekly is not deaf; #54). Optional **grok-talk** (LLM listen+reply;
FR #56, Bob stamps UAT) is off by default: set `grok-talk.json`
`{"grok_talk_enabled": true}` or env `AGENTIC_IRC_GROK_TALK=1` on a seat
after UAT; fuel is peer `weekly` > 0 **or** Cursor Models
`remaining_pct` / aliases on `bob-peers/<id>.json` (not tray `cursor_label`).
Jobs go to `grok-inbox.jsonl`;
completions via `grok-outbox.jsonl` → `outbox.txt`
(`docs/grok-talk-envelope-v1.md`, `scripts/grok_talk_drain.py`).
Watch stays no grok.exe. Recycle Watch-Bobiverse after pull so the
running `irc_agent` loads mention ACK + grok-talk hooks.

Digest `online` is shop JOIN / report POST, not NAMES. A box that
only POINTs on `#bobiverse` still shows `I am offline` in the digest.

## Recycle while a second irc_agent is up

Watch `Test-BobiverseIrcAgentUp` is true if **any** `irc_agent.py` command
line matches `--nick bob-` and private Ergo (`irc.ntsa.uk` or `127.0.0.1`).
Worker homes under `.../workers/...` must **not** satisfy that probe (#70).
A coordinator nick (`{machine}-{pid}`, home `~\.agentic-irc-cursor`) is
separate from `bob-<id>`. Recycle the builder only: stop the process whose
`--nick` is `bob-<id>`; start it from the pulled `scripts\irc_agent.py`
with `--home ~\.agentic-irc-bobiverse`. Leave the extra nick running.
Do not `Stop-ScheduledTask BobFleet-*`. Two agents still need two homes.

Before that start, run deterministic prior cleanup (no LLM): `scripts/prior_irc.py`
or `scripts/Start-BobEar.ps1`. Same `--nick` or same `--home` `irc_agent` processes
are hard-killed, then one process is started with `CreateNoWindow` (not
`Start-Process -WindowStyle Hidden`). Rules: `docs/prior-irc-clean.md`.
A recycle that kills only one `irc_agent` leaves a ghost and the next client
registers a suffixed nick.

## Ionos Ergo down

Service `BobIrcd` runs `C:\ai\ergo\ergo.exe` via NSSM (Automatic, LocalSystem).
Stopped with no `ergo.exe` means the daemon is down. The old task
`BobIrcd-ionos` is gone; do not start it.

```powershell
Start-Service BobIrcd
```

Confirm dual-stack LISTEN on 6697 and TLS handshake `CN=irc.ntsa.uk`.
Do not `Stop-ScheduledTask BobFleet-*` to recover IRC.

## ChanServ — register bob shop channels (FR #313)

**Problem:** without Ergo channel registration, shop rooms are ephemeral; `bob-*`
loses op when the channel empties → KICK gets **482**.

**ionos action runbook:** `docs/ergo-chanserv-enable-bob-shops.md`

1. In the live Ergo ircd yaml (`C:\ai\ergo\…` loaded by `BobIrcd`), enable:

   ```yaml
   accounts:
     authentication-enabled: true
     registration:
       enabled: true
   channels:
     registration:
       enabled: true
   ```

2. `Restart-Service BobIrcd`. Confirm `/msg ChanServ HELP` answers in Halloy.
3. Recycle each `bob-*` Watch ear (current `agentic_irc` main) with
   `BOB_MACHINE_ID` = hostname lower. Log should show
   `INFO chanserv REGISTER #{machine}` (e.g. `#win-mpre8vi4u6u`).
4. `/msg ChanServ INFO #{machine}` — founder should be that `bob-*`.
5. ChanServ requires **channel op** to REGISTER. If the reply is
   `You must be an oper on the channel to register it`, clear other nicks
   briefly so `bob-{machine}` is first JOIN (gets `@`), then REGISTER.

Code path: `scripts/shop_chanserv.py` + `irc_agent._maybe_register_shop_chanserv`
(only `bob-*`, own shop only). Talk seats / `w-*` do not REGISTER.

## Do not

- Point any `bob-*` nick at Libera.
- Run two Watch-Bobiverse processes.
- Open public `:6667` (plain IRC). Public digest GET is `/bob/v1/report`
  (also `/bob/v1/digest`).
- WinRM.
- Stamp UAT (Bob only).
- Use `!bobiverse` to update or read the digest (#174).

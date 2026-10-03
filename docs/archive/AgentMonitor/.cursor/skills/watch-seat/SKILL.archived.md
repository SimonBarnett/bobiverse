<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path .cursor/skills/watch-seat/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: watch-seat
description: >
  Behaviour for the Grok or Cursor agent inside an AgentMonitor watch TUI.
  Use when this session is the watch seat, monitor forwards FROM lines,
  .agentic-irc-watch-cursor / watch-grok, or Simon says watch seat / AgentMonitor agent.
---

# Watch seat

You sit in the Composer / Grok TUI that **Watch-AgentHealth** started. Skill
`agent-monitor` is the monitor contract.

## Visible IRC work (FR #90 Option B)

IRC wakes still run as hidden `agent -p` / Cursor `-p` resumes (same session). The **visible
TUI does not reload** those turns. The operator watches the **wake transcript** pane (or
tails `seat-wake-transcript.log` under the watch state dir) for `wake start` / `wake end`
lines with session, PID, and exit code. That is where ACK/DONE work appears while the TUI
may still show an older seed prompt.

## CAST IRON — watcher auto-pong (Simon 2026-09-23)

The **monitor** (not you) answers every seat-directed `ping` / `PING`
(bare or `nick: ping`) with `PRIVMSG … :nick: pong` on this home's
`outbox.txt`. It does **not** forward that line into the TUI — so a busy
agent still looks alive. Do not also pong from the agent for bare ping.

## CAST IRON — monitor owns `!bored` (Simon 2026-09-25 / FR #100)

The **monitor** posts `PRIVMSG #{machine} :!bored` for you on seat start,
right after your `DONE`, and every few minutes while idle. It never posts
while you are busy (open ACK, pending/hung `agent -p` wake). You must **not**
post `!bored` or busy/idle chatter yourself. Jeeves assigns the next job when
it sees that line; treat a Jeeves assignment (`<nick>: FR|MRB|UAT owner/repo#N <url>`)
like an ASSIGN: ACK on `#{machine}`, do the work, then exact DONE (below).

## ACK / DONE wire (FR #104 / bob-git-accept)

Jeeves only parses lines that **start** with the keyword (after `PRIVMSG #chan :`).
**No nick prefix.** Free text on a **separate** line.

```text
ACK <FR|MRB|UAT> <owner/repo>#<n>
DONE <FR|MRB|UAT> <owner/repo>#<n> [PASS|FAIL] <PR-url>
```

Examples:

```text
PRIVMSG #marchhare :ACK FR SimonBarnett/gh-Jeeves#74
PRIVMSG #marchhare :DONE MRB SimonBarnett/gh-Jeeves#77 FAIL https://github.com/SimonBarnett/gh-Jeeves/pull/80
```

Wrong: `marchhare-42356: ACK …`, `ACK implement …`, `ACK #75 …`, anything after the
DONE URL. **Append** to `outbox.txt` only (`Add-Content` / `AppendAllText`) — never
overwrite (`Set-Content` / `Out-File` without `-Append`). Then **STOP** (monitor `!bored`).

## Loop seat opt-out (FR #103)

`-SeatType loop -Channel '#…' -Nick <non-worker>` (or `-NoBored`) turns off
every monitor `!bored` and the fleet ACK/DONE brief. Use a nick that is **not**
`{machine}-{pid}` so Jeeves never assigns. Health, crash-backoff, and FROM
forwarding still run for that channel only.

## CAST IRON — IRC arrives from the watcher (Simon 2026-09-23)

You are **not** "on IRC" by reading `irc.log`, counting `irc_agent` /
`irc_listen` processes, or arming an in-session `^FROM ` TSR. **AgentMonitor
tails this home's `irc.log` and forwards `FROM` into this session.** That is
how you get IRC. Prefer that wake path (skill `watch-agent-health` /
`agent-monitor-setup`).

When the seat was launched from the Bob Fleet tray **Agents** menu (or
Watch-AgentHealth), the **monitor** already started `irc_agent` + `irc_listen`
on this home and JOINed **its own `#{machine}` ONLY** (CAST IRON 2026-09-25:
workers never join `#bobiverse` or `#agentic_irc`). You respond on the **target channel** in each forwarded
`FROM` via `outbox.txt`.

## Do

1. Treat this home (`.agentic-irc-watch-cursor`, `-2`, `-3`, … `watch-grok`, …)
   as yours only. One seat = one home = one listen = one `irc.log`. Do not share
   another seat's listener. Opening another tray Agents click takes the next
   free slot — it must not kill this seat.
2. Act on monitor payloads (`FROM <nick> <target> <text>`) or what Simon types
   here. Reply on `outbox.txt` if addressed or Simon asked the box. Bare /
   addressed `ping`/`PING` is answered by the **watcher** (auto-pong, no
   agent wake) — even when you are busy.
3. Finish the turn after acting. Do not idle-wait in chat for the monitor.
4. Harvest: `harvest-agent-skills` for fleet/build; IRC playbooks to
   `SimonBarnett/agentic_irc`. AgentMonitor playbooks stay in this repo
   (`.grok/skills/`).

## Do not

- Run, restart, or reimplement `Watch-AgentHealth.ps1` (including starting a
  second IRC stack — the monitor owns ensure-on-launch).
- Tail IRC in-session. Do **not** arm `Get-Content -Wait` /
  `notify_on_output` on every `^FROM ` (burns Cursor turns on `#bobiverse`
  spam).
- Answer "am I on IRC?" by probing logs/processes — answer by whether the
  monitor is forwarding (or just act on the next `FROM`).
- Share another seat's `irc_listen` / `irc_agent` / `irc.log`.
- Stay JOIN'd after the TUI dies. The monitor writes quit files; `irc_agent`
  PARTs then QUITs. Do not restart this seat. A new client is a new slot /
  new nick.
- Use `.agentic-irc-cursor`, `cursor-2`, or `.agentic-irc-bobiverse`.
- Send `!bobiverse`. Stamp UAT. Invent secrets. Gut cards or docs.
- Write another nick's `outbox.txt`.

## IRC

Outbox: UTF-8 no BOM. Only lines starting `PRIVMSG ` go raw; anything else is
`say()` on `#bobiverse`. `JOIN #chan` in outbox is chat, not a JOIN.

<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/killproc/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: killproc
description: >
  End hung agents and roll a replacement process. Use when the user says
  killproc, hung agent, jung agent, end process and roll another, kill the
  deaf talk seat, stuck irc_agent, recycle a hung Cursor TUI seat, or the
  working agent must restart the hung other on this box, or if anyone
  fails to pong the live seat on that box restarts them. Named Grok Bot
  Temporal hangs are unstick-grok-bot. Fleet job queue is grok-build-fleet.
  Talk-seat nick/home rules stay agentic-irc.
---

# killproc

Kill the *named hung seat*, then start a replacement. Do not spray
Stop-Process across every irc_agent / irc_listen / agent.cmd.

## Target

Identify *one* --home and -Nick first (coordinator.pid on that home).
Flamingo examples:

| Seat | Nick | Home |
| First Cursor TUI | flamingo-<seatPid> | ~\.agentic-irc-cursor |
| Second TUI (Agentic Build IRC) | flamingo-<otherSeat> | ~\.agentic-irc-cursor-2 |
| Builder | bob-flamingo | ~\.agentic-irc-bobiverse |

seat= is PowerShell coordinator $PID (issue #88), not python listen/agent.

Hung / "jung" talk seat: 001+JOIN but no pong, listen= empty, or Cursor
killed foreground irc_listen (4294967295). Socket up + deaf is still a
killproc target if Simon said end/roll.

## Do not kill

- The live seat *this* TUI owns (this home's coordinator.pid).
- bob-* / Watch-Bobiverse unless Simon named the builder.
- BobFleet-* scheduled tasks.
- Another seat's --home (same-nick ghost / steal). Skill agentic-irc.
- Halloy. Do not SendKeys into #bobiverse / Halloy.
- Named Grok Bot -> unstick-grok-bot.

## Command

```
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Stop-HungAgent.ps1 -IrcHome "$env:USERPROFILE\.agentic-irc-cursor-2" -Nick flamingo-2224 -Roll
```

-IrcHome is required. Never -Home (PowerShell $Home is read-only).
-Nick required for -Roll. Script stops only irc_agent.py / irc_listen.py
whose command line contains that home.

-Roll starts one new agent (PASS from ~\.grok\ergo\connect.password,
never printed) plus detached irc_listen with stdout
$IrcHome\listen.stdout.log. Writes coordinator.pid.
--channel is #bobiverse,#<machine> from the nick (marchhare-23624 -> #marchhare, not hardcoded #flamingo).

The Cursor TUI for that nick must still arm notify ^FROM on *that* home
(or tail listen.stdout.log). killproc cannot attach another window's TSR.

## Working seat restarts the hung other

Simon: there is still one hung agent on each box -- the other working
agent restarts the other one.

1. You are the live seat. Read your coordinator.pid. Do not kill that home.
2. Hung other on *this* box: Stop-HungAgent -IrcHome <other home> -Roll.
   Typical other home ~\.agentic-irc-cursor-2.
3. If that home is missing (marchhare often seat-1 only), do not invent
   a kill. Say so. A new **build worker** is Watch-AgentHealth only
   (skill `watch-agent-health` / `Start-BobWatchWorker.ps1`). Do not
   Start-TalkSeat a worker.
4. Do not WinRM other boxes. Ask their working nick on #bobiverse to
   killproc their hung home.
5. -Roll is not listening until a Cursor/Grok session wakes on that
   listen.stdout.log. If Simon says not listening: they close the hung
   TUI, then start a new cursor-agent (next section).

## Start a new cursor-agent after close

Simon: hung window gone / start a new cursor agent / irc and build /
try again.

1. Leave this TUI's cursor-agent (node under agent.cmd) alone.
2. Create the replacement **build worker** with Watch-AgentHealth only
   (`Start-BobWatchWorker.ps1 -Kind cursor` or the hidden Desktop
   shortcut). Next free `.agentic-irc-watch-cursor-N`. Own `irc_listen`.
   Do not Start-TalkSeat / cursor-2 for a worker. Do not raw TUI + irc.
3. Shortcuts start hidden (`-Windows off`). Log:
   `%USERPROFILE%\Desktop\Watch-AgentHealth\Watch-AgentHealth.log`.
4. Ping the new watch nick until pong.

Seat create: skill `watch-agent-health`. Talk-seat nick/home facts stay in skill `agentic-irc`.

## After

1. Confirm 001 / nick in that home's irc.log.
2. PRIVMSG <nick> :ping and keep pinging until pong (Simon: ping him
   when you fix).
3. ACK on #bobiverse which nick was killed and rolled.
4. One voice: do not write the killed nick's outbox.txt from this TUI.

## Pointers

- Talk-seat recycle / two homes / why 2nd kills 1st: agentic-irc.
- Builder recycle: bob-irc.
- Skills refresh: reinstall-agentic-build-skills + install_skill.py.

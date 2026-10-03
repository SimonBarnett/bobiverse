<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path .grok/skills/connect-bobiverse/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: connect-bobiverse
description: >
  Join fleet Bob / #bobiverse on private Ergo. Use when Si or an agent says
  join #bobiverse, connect to bob, put a Grok Bot / sand agent on IRC, or
  agents should be able to connect to the bob. Standing join for named Grok Bot
  agents (not bob-* ears). Talk seats stay Start-TalkSeat. Deep detail:
  agentic-irc and bob-irc.
---

# Connect to Bob (#bobiverse)

Private Ergo TLS. Status cleartext. Secrets only as SEAL v2.

## Endpoint (no secrets here)

| | |
|---|---|
| Host | `irc.ntsa.uk` |
| Port | `6697` (TLS) |
| Fleet channel | `#bobiverse` |
| Shop | `#<machine-id>` |
| FR talk | `#agentic_irc` |
| Password | env `AGENTIC_IRC_PASSWORD` or `~/.grok/ergo/connect.password` - never commit |

## Who joins what

| Role | Nick | Channels | How |
|------|------|----------|-----|
| Builder (bob-* ear) | `bob-<machine>` | `#bobiverse` + shop | Watch-Bobiverse / skill **bob-irc** - do not steal this nick or `~/.agentic-irc-bobiverse` |
| Named sand / Grok Bot agent (e.g. Haitch) | **agent name** (bare nick) | `#bobiverse` + shop + `#agentic_irc` | raw `irc_agent.py` with own `--home` (below) - **not** Start-TalkSeat |
| Talk seat (anonymous coordinator seat) | `<machine>-<PowerShell $PID>` | `#bobiverse` + shop + `#agentic_irc` | **Start-TalkSeat** / skill **agentic-irc** |
| Worker | `w-<short>-<pid>` | shop only | never `#bobiverse` |

## Standing join - named Grok Bot / sand agent (CAST IRON)

Named agents (Haitch, etc.) use **nick = agent name**, a **distinct `--home`**, and never bob-* / `~/.agentic-irc-bobiverse`.
Bob's standing Start-TalkSeat recipe is for **talk seats only**, not named sand agents.

On a fleet Windows box with `agentic_irc` + Ergo PASS at `~/.grok/ergo/connect.password`:

```powershell
cd D:\ai\agentic_irc   # or C:\ai\agentic_irc
git pull
python scripts\install_skill.py

$nick = 'Haitch'   # agent name - bare nick, NOT <machine>-<PID>
$home = Join-Path $env:USERPROFILE ".agentic-irc-$($nick.ToLower())"
# or: $home = Join-Path $env:LOCALAPPDATA "agentic-irc-$nick"
$env:AGENTIC_IRC_PASSWORD = (Get-Content "$env:USERPROFILE\.grok\ergo\connect.password" -Raw).Trim()
python -u scripts\irc_agent.py --host irc.ntsa.uk --port 6697 `
  --nick $nick `
  --channel '#bobiverse,#marchhare,#agentic_irc' `
  --home $home `
  --announce-key --hello "$nick-online"
```

- Nick is the **agent name** (e.g. `Haitch`), not `marchhare-<PID>`, not `bob-*`.
- Distinct `--home` per nick. Never `~/.agentic-irc-bobiverse` (never the bobiverse Watch home).
- Prefer at least `#bobiverse`; add shop (`#marchhare`, etc.) and `#agentic_irc` when that was prior practice.
- Detach (Start-Process / background) so the seat keeps running.

## Listen / wake (CAST IRON - no token burn)

The IRC socket stays in `irc_agent.py`. A **separate** listen companion turns PRIVMSG into `FROM ...` lines **without** the Grok/Cursor session busy-polling chat.

1. **Listen (required companion):** after `irc_agent` is up on the named-agent home, start:
   ```powershell
   python -u scripts\irc_listen.py --home $home
   # or: .\scripts\Start-IrcTsr.ps1 -IrcHome $home -Nick $nick
   ```
   `irc_listen.py` tails that home's `irc.log` and prints `FROM <nick> <target> <text>` to `listen.stdout.log`. That is the token-saving path.

**Auto-pong (no token wake):** `irc_agent` itself answers channel `ping` / `ping <nick|partial|bob-*>` with `pong` for bob-* ears and named agents (e.g. Haitch) — not talk seats. No Grok/Watch required for pong.

2. **Wake (prefer):** `Watch-AgentHealth -Grok -IrcHome $home` and/or tray **Agents (Grok)** on that same home. Those poll the listen sink and wake the agent only on new `FROM` lines.

3. **Do NOT** arm an in-session `^FROM` tail, `Get-Content -Wait` on `#bobiverse` spam, or chat-poll IRC from the agent session. That burns Grok tokens on firehose traffic.

`Start-TalkSeat` is for anonymous `<machine>-<PID>` seats only - it rewrites nick. Named agents keep bare nick + raw `irc_agent` + `irc_listen` on their own home.

### Talk seats (not named agents)

Anonymous talk seats still use Start-TalkSeat:

```powershell
.\scripts\Start-TalkSeat.ps1 -MachineId <box> -IrcHome $env:USERPROFILE\.agentic-irc-<seat>
# Nick becomes <machine>-<PowerShell $PID>
```

## Protect / medium-IL note

After `/inheritance:r`, Windows medium-IL (UAC-filtered) tokens need `DOMAIN\USER (OI)(CI)(F)` on the home or `inbox` mkdir fails. See `scripts/protect.py`.

## Related

- **agentic-irc** - talk seats, SEAL, wake, multi-home
- **bob-irc** - fleet builders, Watch-Bobiverse, shops, chair
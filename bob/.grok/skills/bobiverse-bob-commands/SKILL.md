---
name: bobiverse-bob-commands
description: >
  Bob ear command and input reference - recycle routing, shop wire, outbox PRIVMSG, remote console, file transfer, tray restart. Use when sending commands as the bob ear or debugging what the ear does with an input.
---

# bobiverse-bob-commands

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://bob.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

## What the ear handles

| Input | Behaviour |
|---|---|
| `!recycle` / `!recycle <this machine>` typed in a channel | Jeeves (the chair) authorizes and routes it (`RECYCLE v1 <machine>` wire / fleet route); the ear announces the departure, restarts the tray and `ircBob`. Bare `!recycle` and `!recycle all` are fleet-wide: chair-routed only (the ear no longer acts on bare `!recycle` itself) |
| `!recycle dry-run [machine\|all]` | Chair prints the plan; nothing is sent to seats |
| FR #5059 `!recycleseat <nick> [machine]` | Shop or `#bobiverse`: ops (+o/+h), bob-* ear, Jeeves or owner. Ear queues `run\\recycleseat\\req-*.json`; elevated tray stop+verify then start. Stop fail / PID still alive => no new seat + intake report |
| Shop wire in `#<machine>`: `!bored`, `ACK`, `DONE`, `NACK`, `GIVEUP` | Worker <-> Jeeves job assignment (workers JOIN the shop only) |
| `home\outbox.txt` lines `PRIVMSG <target> :<text>` | Sent verbatim (UTF-8, NO BOM, newline-terminated; only complete lines are consumed, offset in `outbox.txt.pos`). Identical send interface on every machine (FR #2174). This is how you "type as the ear" |
| `PRIVMSG <machine>_console :<cmd>` | Remote shell on that box through Airc (`bob-*` ears are allowlisted). **FR #5539:** the ear never splits an over-long console PRIVMSG (overflow fragments would run as a second command). The whole line is dropped; use a shorter command or DCC PUT |
| Incoming channel/PM PRIVMSG | FR #2174: always appended (scrubbed) to `home\inbound-transcript.log` as `UTC channel nick text` — listen without `BOB_IRC_DEBUG` |
| Incoming `*_console` Query `out`/`err`/`DONE` PMs | FR #1546: ear appends them to `<bob home>\airc-replies.jsonl` so `Invoke-AircRemote -ReplyFile` can poll until DONE (skips digest for those lines) |
| FR #4796 driver pacing for `*_console` outbox | `Invoke-AircRemote -OutboxPaceMs` / `-PostBurstCoolMs`; ear `CONSOLE_OUTBOX_FLOOD_S` (env `BOB_CONSOLE_OUTBOX_FLOOD_S`); console token-bucket is FR #4790 |
| Raw shop-op outbox `MODE +/-o|v|h <nick>` / `KICK` / `NAMES` (own shop only) | Ear sends raw IRC via `shop_ops` (FR #4069: `+h` half-op allowed with `+o`/`+v`) |
| `FILE v1 ...` | File transfer handshake via `filexfer.py` (accept/refuse over the outbox) |
| Depart request file | Tray/shortcut writes it; the ear announces departure then quits so the service can restart |

## Using the ear to run Jeeves commands (testing)

Append `PRIVMSG #bobiverse :!help` (and `PRIVMSG #<machine> :!status`) to `home\outbox.txt`; read the replies in the chair's
`cmd-trace.log`. Reference table: `docs/jeeves-commands.md` / skill `bobiverse-jeeves-commands`. Replies are PMs to the ear.

## Tray commands (TipForm)

TipForm menu **Restart** = `Restart-BobTrayWatcher` → `Start-BobFleetTray -ForceNew -SkipServiceRestart` (FR #5111:
relaunch tray only; does **not** restart `ircBob`). Ear-only recycle: `Restart-BobEar.ps1`.
**Reload engine** / `reload` in `<root>\run\tray-cmd.txt`: host `KillEngineTree` + `StartEngine` only (hot-patch).
Ear-only recycle: Start Menu / Desktop **Restart ircBob** or `scripts\Restart-BobEar.ps1` (announce → `Restart-Service ircBob`).
Tray starts with WMI `Win32_Process.Create` so it survives the agent shell; never `Start-Process` it from an agent shell.
Quiet-MSI/SYSTEM installs never start TipForm in session 0 (invisible ghost).

## Verify

```powershell
Get-Service ircBob
Get-Content <ai root>\bob\home\inbound-transcript.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content <ai root>\bob\logs\stdout.log -Tail 40
Get-CimInstance Win32_Process | ? CommandLine -match 'irc_agent.py --nick Bob-' | Select ProcessId,CommandLine   # must contain --host
.\scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot <ai root>\bob
```

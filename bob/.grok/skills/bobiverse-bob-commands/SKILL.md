---
name: bobiverse-bob-commands
description: >
  Bob ear command and input reference - recycle routing, shop wire, outbox PRIVMSG, remote console, file transfer, tray restart. Use when sending commands as the bob ear or debugging what the ear does with an input.
---

# bobiverse-bob-commands

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

## What the ear handles

| Input | Behaviour |
|---|---|
| `!recycle` / `!recycle <this machine>` typed in a channel | Jeeves (the chair) authorizes and routes it (`RECYCLE v1 <machine>` wire / fleet route); the ear announces the departure, restarts the tray and `ircBob`. Bare `!recycle` and `!recycle all` are fleet-wide: chair-routed only (the ear no longer acts on bare `!recycle` itself) |
| `!recycle dry-run [machine\|all]` | Chair prints the plan; nothing is sent to seats |
| Shop wire in `#<machine>`: `!bored`, `ACK`, `DONE`, `NACK`, `GIVEUP` | Worker <-> Jeeves job assignment (workers JOIN the shop only) |
| `home\outbox.txt` lines `PRIVMSG <target> :<text>` | Sent verbatim (UTF-8, NO BOM, newline-terminated; only complete lines are consumed, offset in `outbox.txt.pos`). This is how you "type as the ear" |
| `PRIVMSG <machine>_console :<cmd>` | Remote shell on that box through Airc (`bob-*` ears are allowlisted) |
| `FILE v1 ...` | File transfer handshake via `filexfer.py` (accept/refuse over the outbox) |
| Depart request file | Tray/shortcut writes it; the ear announces departure then quits so the service can restart |

## Using the ear to run Jeeves commands (testing)

Append `PRIVMSG #bobiverse :!help` (and `PRIVMSG #<machine> :!status`) to `home\outbox.txt`; read the replies in the chair's
`cmd-trace.log`. Reference table: `docs/jeeves-commands.md` / skill `bobiverse-jeeves-commands`. Replies are PMs to the ear.

## Tray commands (TipForm)

TipForm menu **Restart** = `Restart-BobTrayWatcher` → `Start-BobFleetTray -ForceNew` (restarts `ircBob` via
`Restart-BobTrayService` / `Invoke-BobTrayServiceControl.ps1`, then relaunches the tray so Start-Bob Sync/ff runs).
Ear-only recycle: Start Menu / Desktop **Restart ircBob** or `scripts\Restart-BobEar.ps1` (announce → `Restart-Service ircBob`).
Tray starts with WMI `Win32_Process.Create` so it survives the agent shell; never `Start-Process` it from an agent shell.
Quiet-MSI/SYSTEM installs never start TipForm in session 0 (invisible ghost).

## Verify

```powershell
Get-Service ircBob
Get-Content <ai root>\bob\logs\stdout.log -Tail 40
Get-CimInstance Win32_Process | ? CommandLine -match 'irc_agent.py --nick Bob-' | Select ProcessId,CommandLine   # must contain --host
.\scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot <ai root>\bob
```

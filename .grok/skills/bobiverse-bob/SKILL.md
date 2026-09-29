---
name: bobiverse-bob
description: >
  Use and maintain ircBob ear, systray, and Watch-AgentHealth on a fleet box.
  Use when Bob service, !recycle, tray restart, ear debug, or /bobiverse-bob.
---

# bobiverse-bob

Foundation: harvest-agent-skills -> https://github.com/SimonBarnett/bobiverse

## Ear

- Service **`ircBob`**, nick **`Bob-{machinename}`**
- Channels: `#bobiverse` + `#{machinename}`
- After Jeeves `!register`: expect **+o** on shop, **+h** on `#bobiverse`
- Agents: nick `{machine}-{pid}`, JOIN **shop only**

```powershell
Get-Service ircBob
Get-Content $env:USERPROFILE\.agentic-irc-bobiverse\irc.log -Tail 80
```

## Systray Restart

Must restart **`ircBob`** (not tray-only): departure announce in `#bobiverse` and `#{machine}`, then Restart-Service ircBob, then tray.

## Recycle

- `!recycle` / `!recycle {machinename}` (this machine): announce → restart systray + `ircBob` (update-check on start)

## Update

`Check-BobiverseUpdate.ps1 -Product bob` on service start unless `BOBIVERSE_NO_UPDATE=1`.

## Do not

- Self-REGISTER shop with ChanServ (Jeeves `!register` only)
- Double-start Watch-Bobiverse ear when `ircBob` is Running

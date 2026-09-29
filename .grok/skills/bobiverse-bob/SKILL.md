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

`Start-BobTray.ps1` (bob MSI) and Desktop **Bob Fleet Restart** call `Restart-BobEar.ps1`:
write `depart-request.txt` → ear announces → `Restart-Service ircBob`.

Watch-AgentHealth installs to Desktop **IF MISSING** from pack `Watch-AgentHealth\`.

## Recycle

- `!recycle` / `!recycle {machinename}` (this machine): announce → restart systray + `ircBob` (update-check on start)

## Update

`Check-BobiverseUpdate.ps1 -Product bob` on service start unless `BOBIVERSE_NO_UPDATE=1`.

## Do not

- Self-REGISTER shop with ChanServ (Jeeves `!register` only)
- Double-start Watch-Bobiverse ear when `ircBob` is Running

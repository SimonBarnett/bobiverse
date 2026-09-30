---
name: bobiverse-airc
description: >
  Maintain Airc console service. Use when airc MSI, {machinename}_console,
  domain/workgroup lobby, AircConsole leftover, remote PRIVMSG shell, or
  /bobiverse-airc.
---

# bobiverse-airc

Foundation: harvest-agent-skills -> https://github.com/SimonBarnett/bobiverse

## Service

- Service **`Airc`**, tree `C:\ai\airc`
- Nick **`{MachineId}_console`** (MachineId = sanitized lowercase hostname / `BOB_MACHINE_ID`)
- JOIN **`#{MachineId}`** if ChanServ-registered; else **`#{domain|workgroup}`**
- Console home: `%USERPROFILE%\.airc` (often Administrator when NSSM is LocalSystem)

```powershell
Get-Service Airc,AircConsole
Get-Content $env:USERPROFILE\.airc\*.log -Tail 40 -ErrorAction SilentlyContinue
```

## Airc vs AircConsole

- bobiverse **Airc** UpgradeCode is distinct from agentic_irc **AircConsole** (issue #12).
- Prefer **one console per box**. Install-Airc **removes** leftover `AircConsole` from the SCM.
- Roots: `C:\ai\airc` / service `Airc` vs `C:\ai\airc-console` / `AircConsole`.

## Remote shell via PRIVMSG

Authenticated fleet ears (`bob-*`) may:

```text
PRIVMSG win-mpre8vi4u6u_console :sc query ircJeeves
```

- Shell is **cmd.exe** under the service account (often `nt authority\system`).
- Keep each command **short** (IRC line length); avoid nested multiline PowerShell in one PRIVMSG.
- Stage scripts with `irm <gist-raw> -OutFile C:\ai\drop\….ps1` then `powershell -File …`.
- Killing broad `powershell.exe` on the box can take down Airc’s own host process — target `Start-Jeeves` / specific PIDs only.
- After a kill, `Restart-Service Airc` on the box until `{machine}_console` is visible on IRC again.

## Install / secrets

- After public MSI: `C:\ai\airc\config\ergo.password` (or `~\.grok\ergo\connect.password`).
- Re-run `Install-Airc.cmd -MachineId <id>` after MSI if NSSM still points at an old tree.
- Self-update: `Check-BobiverseUpdate.ps1 -Product airc` on start.

## Do not

- Invent Ergo PASS
- Run Airc and AircConsole both as live consoles on the same machine
- Stamp UAT

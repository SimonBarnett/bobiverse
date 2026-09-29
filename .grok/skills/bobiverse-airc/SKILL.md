---
name: bobiverse-airc
description: >
  Maintain Airc console service. Use when airc MSI, {machinename}_console,
  domain/workgroup lobby, or /bobiverse-airc.
---

# bobiverse-airc

Foundation: harvest-agent-skills -> https://github.com/SimonBarnett/bobiverse

## Service

- Service **`Airc`**, tree `C:\ai\airc`
- Nick **`{machinename}_console`**
- JOIN **`#{machinename}`** if ChanServ-registered; else **`#{domain|workgroup}`**

```powershell
Get-Service Airc
Get-Content $env:USERPROFILE\.airc\*.log -Tail 40 -ErrorAction SilentlyContinue
```

Self-update: `Check-BobiverseUpdate.ps1 -Product airc` on start.

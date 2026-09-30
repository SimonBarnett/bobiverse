# AGENTS — airc (bobiverse)

Product tree: `C:\ai\airc`. Service: **Airc** (nick `{MachineId}_console`).

## Read first

- `.grok/skills/bobiverse-airc/SKILL.md` — lobby/shop, AircConsole leftover, remote shell
- `.grok/skills/harvest/SKILL.md` — promote lessons back to SimonBarnett/bobiverse
- `docs/post-install.md` — Ergo PASS, bootstrap, verify
- `docs/airc-ops.md` — shop vs lobby, PRIVMSG shell, UpgradeCode notes

## Boundaries (CAST IRON)

- This MSI is **airc only**. Distinct UpgradeCode from agentic_irc **AircConsole**.
- Prefer one console per box; Install-Airc removes leftover `AircConsole` from SCM.
- Roots: `C:\ai\airc` / `Airc` vs `C:\ai\airc-console` / `AircConsole`.

## Common ops

```powershell
Get-Service Airc,AircConsole
Get-Content $env:USERPROFILE\.airc\*.log -Tail 40 -ErrorAction SilentlyContinue
# re-bind after MSI if NSSM still points at old tree:
.\scripts\Install-Airc.cmd -MachineId <id>
```

JOIN `#{MachineId}` when ChanServ-registered; else domain/workgroup lobby.

## Do not

- Run Airc and AircConsole both as live consoles on the same machine
- Invent Ergo PASS or stamp UAT
- Kill broad `powershell.exe` when diagnosing — can take down Airc’s host process

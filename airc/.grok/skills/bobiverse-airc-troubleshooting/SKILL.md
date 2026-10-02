---
name: bobiverse-airc-troubleshooting
description: >
  Debug playbook for the Airc console - NickServ GUID/SASL 904, Default-profile home, lobby vs shop, AircConsole leftover, NSSM re-point. Use when {machine}_console is missing or misbehaving.
---

# bobiverse-airc-troubleshooting

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

Start with `bobiverse-fleet-ops`. Airc-specific lessons:

| Symptom | Diagnosis / fix |
|---|---|
| `sasl-fail 904` / `433`, `<machine>_console` reserved | Wrong NickServ GUID vs the console home in use. Oper `NickServ PASSWD <machine>_console <value from console.password>` then `Restart-Service Airc`. `ERASE` needs `/OPER` + `accreg`. |
| Console home is `C:\Users\Default\.airc` | Quiet MSI as LocalSystem picked the Default profile and orphaned the GUID. Use `C:\Users\Administrator\.airc` or `<ai root>\airc\home` (Install-Airc does this now). |
| Console joins the lobby, not the shop | `#<machine>` not registered in ChanServ (Jeeves `!register <machine>`), then restart `Airc`. |
| Two consoles fighting | `AircConsole` (agentic_irc) still installed - `Install-Airc` removes it from the SCM; check `Get-Service Airc,AircConsole`. |
| Service runs an old tree | NSSM path stale - `Install-Airc.cmd -MachineId <id>`. |
| Console vanished after a broad `Stop-Process powershell` | Airc's host died; `Restart-Service Airc`. |
| Command reply truncated | Prefer FR #75 chunked `out`/`DONE` framing; use `Invoke-AircRemote.ps1 -Action Psb64` / PUT (FR #76/#78) instead of gist+irm. |

Finish every session with the harvest step.

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
| MSI upgrade minted a new ConsoleHome / lost GUID | Upgrade skipped live `AppParameters` / `airc-install.json` and fell through to a profile default. Preserve identity: live AppParameters → install.json → defaults last (FR #1552 / #1583). |
| Console joins the lobby, not the shop | `#<machine>` not registered in ChanServ (Jeeves `!register <machine>`), then restart `Airc`. |
| Two consoles fighting | `AircConsole` (agentic_irc) still installed - `Install-Airc` removes it from the SCM; check `Get-Service Airc,AircConsole`. |
| Service runs an old tree | NSSM path stale - `Install-Airc.cmd -MachineId <id>`. |
| Console vanished after a broad `Stop-Process powershell` | Airc's host died; `Restart-Service Airc`. |
| Command reply truncated | Prefer FR #75 chunked `out`/`DONE` framing; use `Invoke-AircRemote.ps1 -Action Psb64` / PUT (FR #76/#78) instead of gist+irm. |
| `-ReplyFile` times out / never sees `DONE` | Ear must be capturing `*_console` Query lines into `<bob home>\airc-replies.jsonl` (FR #1546). Confirm the helper prefixed `id=<8hex>`, the jsonl path resolves beside Outbox / `BOB_HOME` / `<ai root>\bob\home`, and ircBob is running. Do not expect a static pre-written ReplyFile. |
| Console log floods with keepalive PING / no timestamps / wrong path | AppStdout should be `<ai root>\airc\logs\airc-console.log` with rotate; service uses ISO-UTC + `info_keepalive` (~1/hour). Reinstall or `nssm set Airc AppStdout ...` after merge if live box still points at an agent folder. |
| DisplayName still `#{machine}` | `Install-AircConsole.ps1` expands DisplayName/Description with machine id. Re-run install or set NSSM DisplayName after upgrade. |

Finish every session with the harvest step.

## FR #2355

| DisplayName still literal #{machine} or ConsoleHome under Users\Default | Old NSSM bake / FR #1552 prior-identity restore of Default home | Heal DisplayName with expanded MachineId; migrate home to <ai root>\airc\home and update AppParameters; Install remaps Default after prior restore (FR #2355). |


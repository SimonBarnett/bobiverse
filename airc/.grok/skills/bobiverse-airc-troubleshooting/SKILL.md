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
| Long Command stalls after `out … seq=1` (no further lines / no DONE) | Often Airc restart mid-emit (`probe interrupted -> stop` in `airc-console.log`). FR #2612: outbound queue + stop DONE flush. Check console log for stop/reconnect during the Wait; avoid hotpatch Restart-Service while ReplyFile runs; raise `-TimeoutSec` for large line counts. |
| Second concurrent `Invoke-AircRemote` gets `busy` + exit=1 | Pre-#2632 airc fail-closed on overlap. Tip queues per Query (FR #2632); hotpatch/rebuild airc so `ShellJobRunner` queues, or rely on Invoke-AircRemote busy retry (`-MaxRetries`). Overflow still busy-fails when pending_max is full. |
| `-Action Status` timeout / empty StdOut / `DONE` id mismatch / PS splat `@machine_console` (FR #2570 / #2575) | Client relayed bobtalk `Heard:` line into the console; or Status lacked `id=` / DONE; or body was bare `STATUS` (StdOut empty). Fixed: sanitize Heard:/@nick noise; Status sends `id=… STATUS`; console replies `out id=… seq=1 STATUS machine=…` then `DONE id=… exit=0`. Use ear `airc-replies.jsonl` only — a different `.jsonl` path is an empty Wait. |
| Command StdOut mangles Greek/CJK to `a` / U+FFFD / `?` (FR #2580) | Redirected powershell.exe `$OutputEncoding` was ASCII (best-fit). Fixed: `encode_ps_encoded_command` / `psb64` wrap UTF-8 OutputEncoding; `cmd:` prefixes `chcp 65001`. Hotpatch `airc_console.py` + Restart-Service Airc (or tip MSI). |
| Every Command StdErr has `#< CLIXML` / `Preparing modules for first use` (FR #2641) | Redirected powershell.exe progress records. Fixed: EncodedCommand preamble sets `$ProgressPreference='SilentlyContinue'`. Frozen `airc.exe` needs rebuild/redeploy; source `run_shell_request` path is clean. |
| Command StdErr is `#< CLIXML` / `<Objs>` / `_x000D__x000A_` with the real error buried (FR #2910) | PowerShell 5.1 error-stream CLIXML under redirect (progress silence from #2641 does not decode Error records). Fixed: `plain_text_powershell_stderr` in `run_shell_request`; preamble statements on their own lines. Hotpatch `airc_console.py` + Restart-Service Airc, or tip MSI / rebuild frozen `airc.exe`. |
| Console log floods with keepalive PING / no timestamps / wrong path | AppStdout should be `<ai root>\airc\logs\airc-console.log` with rotate; service uses ISO-UTC + `info_keepalive` (~1/hour). Reinstall or `nssm set Airc AppStdout ...` after merge if live box still points at an agent folder. |
| DisplayName still `#{machine}` | `Install-AircConsole.ps1` expands DisplayName/Description with machine id. Re-run install or set NSSM DisplayName after upgrade. |

Finish every session with the harvest step.

## FR #2355

| DisplayName still literal #{machine} or ConsoleHome under Users\Default | Old NSSM bake / FR #1552 prior-identity restore of Default home | Heal DisplayName with expanded MachineId; migrate home to <ai root>\airc\home and update AppParameters; Install remaps Default after prior restore (FR #2355). |

| Stop mid-Command: ear got out/err but **no DONE**; log `session interrupted` + `10038` / `send: no socket` | FR #2640/#2649: prepare_stop drains DONE with **no FLOOD_S gap**, sets `_stop_flushed` so finally does not re-flush after sock=None. Hotpatch `airc_console_service.py` + Restart-Service Airc (frozen `airc.exe` needs rebuild). |

## Harvest digest (lessons audit 2026-10-06)

Generalised from 18 harvested lessons that never reached this book (audit for FR #2705). The per-lesson table is in `common/docs/harvest-lessons-audit-2026-10-06.md`.

- **Console job protocol:** background emits must swallow ConnectionError on a dead IRC socket and force a reconnect, and handle KeyboardInterrupt explicitly on service stop. STATUS pins `id=` and frames output as `out id= seq=` followed by `DONE id=`. Sanitize bobtalk/Halloy `Heard:` wrappers, but never strip PowerShell `@(`, `@'` or `@"`. ReplyFile must be the ear's `airc-replies.jsonl`. Queue replies across reconnects and flush DONE on stop. UPDATE replies first, then schedules a detached Apply; never run msiexec in the console process. Frozen airc.exe keeps Start-AircConsole ServiceMode parity (Sync, then Update). (18 lessons: harvest #2167, #1614, #1600, #1599, #1594, #1586 +3 more, 9 held intake rows)

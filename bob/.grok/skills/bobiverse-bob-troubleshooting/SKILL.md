---
name: bobiverse-bob-troubleshooting
description: >
  Debug playbook for the Bob ear - restart loops (missing --host), SASL/NickServ password reset, outbox BOM, no ops, tray problems, digest POST. Use when ircBob misbehaves.
---

# bobiverse-bob-troubleshooting

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

Start with `bobiverse-fleet-ops` (health checks, hotpatch rules, known-failure table). Ear-specific lessons:

| Symptom | Diagnosis / fix |
|---|---|
| Ear restarts every 30-60 s (new `ircBob-stdout-*.log` files, repeated `GRANT +h`) | The watcher/tray kills any `irc_agent.py --nick Bob-*` whose command line lacks `--host`. `Start-Bob.ps1` now passes `--host <IrcHost>` and the MSI bakes `-IrcHost` into NSSM. Hand-fix on an old install: add `--host irc.ntsa.uk` in `Start-Bob.ps1`, `Restart-Service ircBob`. |
| `NICKNAME_RESERVED` / `sasl-fail 904` | `home\nickserv.password` does not match the registered account. Oper `NickServ PASSWD bob-<machine> <value from the file>`; never create a new GUID for a registered account; restart `ircBob`. |
| SASL never attempted | Missing/unreadable `nickserv.password` (BOM or ACL). The file must be one line, no BOM. |
| Outbox lines not sent | Ear home outbox: BOM or a partial last line (no `\n`), or LocalSystem-ACL only so your user cannot append - use a user-writable home. **Seat** outbox: check `worker.log` for `outbox: sent`. The seat outbox is drained by move-aside every 0.5 s, has no `.pos`, and is normally empty — never treat an empty file as proof a DONE was already sent (FR #2876). |
| Ear joined but no ops | Shop not registered: Jeeves `!register <machine>`; then `!resync`. |
| Tray **Agent** / **Plan** click does nothing, or the seat vanished | Read `%LOCALAPPDATA%\Bobiverse\worker\logs\bob-worker-agent.log` and the tray log `%USERPROFILE%\.grok\long-running-background-tasks\watch_bob_tray.log` (`worker exe missing` = reinstall the MSI; exit 3 = IRC lost, the exe kills its own agent and ends on purpose; exit 5 = restart limit). Every click starts a NEW agent - never resume. Full table: `bobiverse-bob-worker`. |
| Worker seat vanished; parent unknown after exit | `parent_of` after `proc.wait()` is empty. FR #1643 captures create-parent at `start_agent`; bin refresh defers locked hashed exe delete (harvest #1678 / PR #1658). |
| Worker console waits for Enter after Jeeves inject (`relay: injected`) | Frozen `bob-worker.exe` pre-dates FR #1601 submit gap. Press Enter to unblock; rebuild exe + new Agent seat for the durable fix (harvest #1605). |
| Tray shows twice / wrong icon | Old installers left top-level `Bob Systray` links; the new installer keeps ONE Start Menu folder `Bobiverse` and deletes the rest. |
| Tray dies when the agent shell exits | It was started with `Start-Process`; use `Start-BobTray.ps1` (WMI create). |
| TipForm **Restart** vs ear-only recycle | Menu **Restart** -> Restart-BobTrayWatcher -> Start-BobFleetTray -ForceNew (restarts ircBob + relaunches tray). Ear-only: Start Menu **Restart ircBob** / scripts\\Restart-BobEar.ps1. Do not document TipForm Restart as calling Restart-BobEar.ps1 directly (drift fixed in FR #154). |
| Autostart/ONLOGON killed seats on logon | Missing -SkipTidy on tray shortcuts. FR #1636: autostart uses -ForceNew -SkipTidy; TipForm **Restart** remains the tidy path (harvest #1663). Watchdog relaunch (Ensure-BobTrayRunning) also ForceNew+SkipTidy (FR #1642 / #1681). |
| TipForm stale `{nick}: {work}` while workers active | Callback flap and/or `Get-BobTrayHover` hung the poll thread so `tray-status.json` froze (FR #1553 / harvest #1562). Confirm `Sync-BobTrayStatusWorkersFromDigest` + non-UI timer on main (PR #1576); heal `:7700` with `Start-BobCallbackSupervised.ps1`; compare TipForm vs queue ACC / stuck_accepted. Never block worker refresh on hover. |
| TipForm empty while digest has seats | Peer merge blanked `working_on` without rolling `worker_list` (PR #1495) or nick-map ignored `.work` (PR #1555). Check export fields + `bobreport._roll_working_on`. |
| Seat-wrapper kill removed a diagnosing shell | Never `match Watch-BobTray` broadly; the filter is `-File ...Watch-BobTray.ps1`. |
| Service shows old code after MSI | NSSM path/params stale - re-run `Install-Bob.ps1`; check `<ai root>\bob\VERSION`. |
| Digest POST fails | Machine not on the roster Jeeves publishes, or `reportUrl` unreachable. `Assert-BobDigestWebhookLocal.ps1`; `GET https://irc.ntsa.uk/bob/v1/report` should be 200. |
| `GET https://irc.ntsa.uk/bob/v1/digest` returns 404 | Expected on the public IIS front-door (FR #149). Public digest JSON is `GET https://irc.ntsa.uk/bob/v1/report`. Local bobcallback on `:7700` still answers `/bob/v1/digest` and `/digest` with the same body. |
| Need to check NSSM env (e.g. `BOBIVERSE_NO_UPDATE`) | Do **not** run `nssm get ircBob AppEnvironmentExtra` and print the raw block - it includes `AGENTIC_IRC_PASSWORD` (FR #147). Print key names only (split on first `=`). See `bobiverse-fleet-ops` hotpatch rule. |
| `!startworker` NACKs `nobody is logged in` while `InstallRoot\run\startworker\tray.alive` is fresh | Frozen `bob-ear.exe` resolved install root via `Path(__file__).parent.parent` under `_MEIPASS` (often `C:\Windows\Temp\_MEI*`), so the ear looked for `Temp\run\startworker` (FR #2666 / PR #2671). Confirm `Start-Bob.ps1` exports `BOB_INSTALL_ROOT=$InstallRoot` before launch; restart `ircBob` so the env is picked up. Full frozen-aware resolve needs a rebuilt `bob-ear.exe` (`resolve_bob_install_root` / `--install-root`). Do not treat a fresh tray.alive under InstallRoot as proof the ear sees it until the root is correct. |
| Tray worker env differs from CLI (`C:\\Users\\...` doubled `BOB_*_HOME`, or unexpected `CURSOR_*`/`SAND_*`) | `Start-BobFleetTray` seat wrappers used to double backslashes in env assigns (FR #2669 / PR #2680). Confirm wrapper uses single-quoted path assigns and `hasDoubledEnv` rewrite; restart tray via `Start-BobFleetTray`. `bob-worker` `prepare_seat_child_env` merges `extra` then normalises `BOB_*` paths and scrubs `CURSOR_*`/`SAND_*` **after** the merge (FR #2683 / PR #2690) so a hostile overlay cannot reintroduce agent-host keys (needs rebuilt `bob-worker.exe` for the scrub path). |

Finish every session with the harvest step.

---
name: bobiverse-bob
description: >
  Use and maintain the ircBob ear, tray and shop on a fleet box. Architecture, paths, channels, config, logs, tray, install/upgrade/hotpatch. Use in <ai root>\bob or for the Bob service, tray restart, ear debugging, SASL/NickServ, or /bobiverse-bob.
---

# bobiverse-bob

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

Foundation: `bobiverse-fleet-ops` (shared ops/hotpatch/health) and `harvest` -> https://github.com/SimonBarnett/bobiverse

## Architecture

`ircBob` runs `Start-Bob.ps1` -> prefer `scripts\bob-ear.exe` (FR #1481 self-contained ear) else `python -u irc_agent.py` with `--nick Bob-<machine> --home <home> --channel #bobiverse,#wonderland,#<machine> --host <irc host>` (FR #3834). Pack builds the exe via `Build-BobEar.ps1`; `Install-BobEarExe.ps1` swaps it with `.bak` rollback.
(NSSM). The ear is the box's presence on IRC: it keeps the shop channel, reports status to the digest, executes `!recycle`
for its own machine, drains `home\outbox.txt`, and hosts the talk seats. The **TipForm tray** is an interactive companion
(not a service, not a `BobFleet-*` task). Digest POSTs need no secret (roster-gated by Jeeves).

| Piece | Where |
|---|---|
| Install root | `<ai root>\bob` (`scripts\`, `tools\` TipForm, `src\` BobBridge, `assets\bob-systray.ico`, `config\`, `logs\`, `.grok\skills\`, `PIN.txt`, `VERSION`, **`VISION.md`** for MRB/UAT — FR #1615) |
| Ear home | `<ai root>\bob\home` (LocalSystem) else `~\.bobiverse`; `outbox.txt` (+`.pos`), **`inbound-transcript.log`** (always-on scrubbed PRIVMSG: channel/nick/text, FR #2174), `irc.log` (raw wire only with `BOB_IRC_DEBUG=1`), `nickserv.password`, `accounts.json`, `digest.json` |
| Logs | `<ai root>\bob\logs\stdout.log` / `stderr.log` (rotated `ircBob-*` files) |
| IRC | channels `#bobiverse` + `#wonderland` + `#<machine>` (identical on every box; FR #3834); nick `Bob-<machine>`; SASL user `bob-<machine>`; host passed explicitly with `--host` (Start-Bob `-IrcHost`, default `irc.ntsa.uk`). Workers/seats JOIN the shop only (never `#wonderland`). **DIGEST_ID_FOLD:** `ionos`->`win-mpre8vi4u6u`, `dev1`->`ce-priority-dev1` — never JOIN/`--channel` `#ionos` (harvest #2280 / PR #2279) |
| Config | `config\ergo.password` (server PASS; FR #3904 also resolves sibling `airc`/`jeeves` config and seeds a local copy), `home\nickserv.password` (SASL; upgrade migrates from prior BobHome / `\.bobiverse` and fails MSI 1603 if missing), `service.password`/`BOBIVERSE_SERVICE_PASSWORD` (DPAPI logon). NSSM AppStdout/AppStderr → `logs\stdout.log` / `stderr.log` (FR #3904). |
| Tray | `scripts\Start-BobTray.ps1 -> tools\Start-BobFleetTray.ps1`; HKCU `Run\BobiverseTray`; per-user Startup shortcut; quiet MSI uses the ONLOGON `/IT` task `BobiverseTray`. Autostart/shortcuts/ONLOGON default **`-ForceNew -SkipTidy`** (FR #1636 / harvest #1663): replace the prior tray only; leave seats/Grok Bot running. |
| TipForm **Restart** | Menu label **Restart** -> `Restart-BobTrayWatcher` -> `Start-BobFleetTray -ForceNew` (restarts `ircBob` via `Restart-BobTrayService`, then relaunches tray; **this** path still tidies seats). Ear-only: Start Menu **Restart ircBob** / `scripts\Restart-BobEar.ps1` |
| Agent / Plan | Tray items **Agent** and **Plan** (single click, no submenu) run `worker\bob-worker.exe` (via a per-user run-copy) -> a NEW agent each click, never resumed. Guides: `bobiverse-bob-worker`, `bobiverse-bob-plan` |
| Start Menu | ONE all-users folder `Bobiverse`: Bobiverse Tray, Restart ircBob (ear-only via `Restart-BobEar.ps1`), Bob Services, Logs, Skill books, Agent guide (all systray icon) |

## Listen and send (FR #2174)

- **Listen:** `Get-Content <bob home>\inbound-transcript.log -Tail 40` — always-on rotating transcript (`UTC channel nick text`, secrets redacted). Independent of `BOB_IRC_DEBUG`.
- **Send:** append `PRIVMSG <target> :<text>` to `<bob home>\outbox.txt` (UTF-8 no BOM). Same outbox contract on every machine.
- **Worker filter:** `bob-worker` still only injects FROM Jeeves addressed to that seat; other lines remain visible in the transcript.
- **Recovery:** absent `ircBob` -> Install-Bob / Start-Service; stale `irc_listen.py` -> retire and use ircBob; running without transcript -> `Restart-BobEar.ps1` after deploy.

## Roles

- After Jeeves `!register <machine>` the ear is +o in `#<machine>`, +h in `#bobiverse`, and +o in `#wonderland` (Jeeves grants; FR #3834). Agents (`<machine>-<pid>`) JOIN the shop only — never `#wonderland`.
- The ear nick `Bob-<machine>` is ALSO an authorized principal for Jeeves ops commands (`!focus`, `!ignore`, `!sweep`, `!resync`, `!recycle`).
- Product Sync/ff and self-update run on **ircBob start** only; the tray never updates the tree.

## Install, upgrade, rollback, hotpatch

See `bobiverse-fleet-ops`. Bob specifics: hotpatch = back up `<ai root>\bob`, copy changed `scripts\*`, `Restart-Service ircBob` (or
`Restart-BobEar.ps1`, which announces the departure first). Do not kill seats/agents or the tray to apply a patch. `Start-Bob.ps1`
must pass `--host` or the watcher/tray treats the ear as foreign and kills it (restart loop).

## TipForm worker lines (FR #1553 / harvest #1562)

TipForm paints `run/tray-status.json` (`grok[].workers`). Stale `{nick}: {work}` while seats are busy is usually **not** stuck workers.

Common failure chain:

1. BobCallback down (`http://127.0.0.1:7700/bob/v1/report` HTTP 000) so live digest GET fails.
2. `Get-BobTrayHover` hangs on the WinForms poll thread (peer DNS/UNC) so `Write-BobTrayStatusSnapshot` never runs.
3. Digest `worker_list` lags ACC (orphan doing/offered).

Durable rules (code in `BobTrayDialogs.ps1` / `Watch-BobTray.ps1`, PR #1576):

- Never let `Get-BobTrayHover` block TipForm worker refresh.
- Stale `working_on` after DONE with empty queue `accepted` can trip `seats_stuck_doing` (harvest #1712) — false busy; next digest POST clears it.
- `Sync-BobTrayStatusWorkersFromDigest` — report/digest-only sync (bounded timeout) rewrites `grok[].workers` without calling hover.
- Call sync **before** `Update-Hover` on each poll; keep a **non-UI** timer (~10s, `SynchronizingObject=$null`) so worker lines keep moving while hover is stuck.
- When BobCallback is down, still prefer local chair files (`digest.json` + queue ACC) over a hung hover path.
- NAK busy after DONE: digest `machines.workers` map can stay `running`/`working_on` while `worker_list` is idle (harvest #1715); clear both maps → product FR #1714.
- Empty TipForm while digest has activity: peer merge must roll `working_on` from `worker_list` (PR #1495); nick-map/digest readers must accept `.work` / `.job` / `.working_on` (PR #1555).

Troubleshoot: compare TipForm vs `Invoke-JeevesMonitorCheck -Check stuck_accepted` / queue ACC; heal BobCallback with `Start-BobCallbackSupervised.ps1` (single owner). See `bobiverse-bob-troubleshooting`.

## Do not

- Self-REGISTER the shop with ChanServ (Jeeves `!register` only); mint a fresh NickServ GUID for a registered `bob-*` account.
- Double-start the ear when `ircBob` is Running; kill broad `powershell.exe`/`python.exe`; stamp UAT; invent an Ergo PASS.

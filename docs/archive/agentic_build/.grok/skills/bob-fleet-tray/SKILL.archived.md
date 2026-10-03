<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-fleet-tray/SKILL.md, last changed 2026-09-30. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-fleet-tray
description: >
  System tray icon for Bob Fleet / bobiverse on this Windows box: hidden
  PowerShell NotifyIcon, Font Awesome robot, dark TipForm card. Use when the
  user says tray icon, system tray, Bob Fleet card, #Bobiverse, systray,
  NotifyIcon, flash the watcher, recycle tray, TipForm n/a, MarchHare Cursor
  pools, digest pcent, or /bob-fleet-tray. CAST IRON: Cursor pool check is
  LOCAL Spending (box-usage); digest must not decide pool remaining.
  Stall policy is bob-fleet-monitor. Do not invent usage numbers.
---

# Tray (Bob Fleet / #Bobiverse)

`tools/Watch-BobTray.ps1` is the human monitor. Card title is
`#Bobiverse (<machineId>)` from `Get-ThisMachineId` / `$env:BOB_MACHINE_ID`
(bobiverse nick: ionos / flamingo / marchhare / ce-priority-dev1), not the
Windows hostname and not the old "Bob Fleet" string.

When `config/bobiverse.json` has `nicks`, the card lists **only those machine
ids** plus this host if it is one of them. Never a ghost IRC-derived name
(`marchhare-bugets`). Without nicks (hermetic tests), fall back to
`config/fleet-registry.json` + `{BOB_BRIDGE_HOME}\fleet\registry.json`.
Transport is read-only filesystem peek plus IRC moot roster. No WinRM.
See `docs/bob-fleet-peer-peek.md`. Tiles may show `not in moot` or
`lastSeen stale`; do not invent `unreachable` for a seat that is merely
not in the moot.

## Seat deals (next to the name)

`config/bob-seats.json` (and/or `config/fleet-registry.json` `seats`) maps
machines to xAI seats. Tile heading is `MACHINENAME - SEAT (N%)`:

| Seat label | Account | Machines |
|---|---|---|
| Smart Catalogue | social@smartcatalogue.uk | ionos |
| Club Madeira | social@clubmadeira.uk | flamingo |
| ntsa | si@ntsa.uk | marchhare, ce-priority-dev1 |

Machines on the **same seat share one weekly remaining %** (account-level).
Do not show divergent % for marchhare vs ce-priority-dev1. Prefer the
conservative (lowest) known remaining for that seat.

Never set `XAI_API_KEY` on DEV1 as a **User/Machine** persistent env; both
ntsa boxes use OIDC session (`si@ntsa.uk`). Exception: when TipForm/Agents
**Start Agent (Grok)** sees this machine's Grok weekly remaining at **0%**,
offer a session-only API key dialog and pass `XAI_API_KEY` to the
**child** `Watch-AgentHealth` process only (`ProcessStartInfo`, never
`SetEnvironmentVariable` User/Machine, never rewrite `auth.json`).

Named xAI seats (`smart-catalogue`, `club-madeira`, `ntsa`) stay per-seat.
They are not Cursor spending bars.

## Cursor spending groups

**Three groups** on the card (not xAI seat names; issue #151).

1. `grok chat  {N%|n/a}` -- Sand (`GetSandUsageStatus.usagePercent`). Digest aliases `grok-weekly`, `sand` map here.
2. `high cost models  {N%|n/a}` -- `planUsage.apiPercentUsed` (named models). Digest alias `other-models` maps here. Never pick Other Models as a worker fuel (`bob-token-handoff`).
3. `Low cost models  {N%|n/a}` -- TipForm label for wire id `auto` (`planUsage.autoPercentUsed` / Auto picker / Cursor Models / `autoBucketModels`). Id stays `auto` for cache/wire compat. MRB/PR fuel gate. Reset + `?` help on every row.

Do **not** paint an **on-demand** bar. On-demand is spend-limit pay-as-you-go
after included. Header **overspend** (GBP, right-aligned in the tile host)
is enough. When the model is Auto, the meter is **Low cost models** (id `auto`), not on-demand.

Do **not** collapse groups into one `Cursor Models` strip. Do **not** prefix
those rows with xAI seat labels.

### CAST IRON — pool check is LOCAL (Simon 2026-09-27 / AgentMonitor #150)

**Agents start / fuel / "is there pool?"** must use **local** Spending
(`Get-BobCursorAgentWeeklyRemaining` / `GetCurrentPeriodUsage` /
`planUsage.autoPercentUsed`). **Never** GET the digest report (or trust
digest `cursor_pools` / `pcent`) to decide whether a Cursor pool has
remaining. TipForm bars on a host with a Cursor login paint from that
local doc first. Digest `pcent` may only **fill still-null** bars (hosts
with no Cursor login, e.g. MarchHare). Digest must **not overwrite** a
known local/cache value.

**Overspend + this host's Grok weekly** (AgentMonitor #150 / agentic_build
#423): TipForm `overspend £N.NN` is local `spendLimitUsage` only
(`Get-BobCursorOverageGbp`). This host's Grok Build weekly tile is local
`unified.jsonl` (`Get-BobWeeklyRemaining`); digest must not clobber it.
Publish path (`Write-BobIrcStatus` → digest `overage_gbp` / `weekly`) stays
unchanged for peers.

Hosts that do have a login (ionos, flamingo) still **publish** `pcent` **and**
per-pool `cursor_pools` (with `period_end`) plus `sand_period_end` via
`Write-BobIrcStatus` so MarchHare can fill nulls with the correct reset clocks
(issue #456). Shape/POST checklist: `bob-digest-webhook`. Do not invent a
percent. Missing is `n/a`. `0%` is a real value.

`account_remaining_pct` on `Get-BobTrayHover` is the **auto** remaining
(MRB fuel gate), filled from **local** Cursor first. Machine rows are
Grok Build weekly + fuels (`cursor-models`, `grok-build`, `copilot`,
`grok-bot`).

- Known remaining: each group bar shows N% from Spending (see `box-usage`), not Sand overage mislabelled as auto.
- Do **not** label Grok Bot Sand overage as Cursor Models remaining. Overage GBP from `GetCurrentPeriodUsage.spendLimitUsage.individualUsed` (USD cents to GBP FX, not `tip_cursor.json`) is a separate signal. Show it as overspend, not as the fuel remaining figure. **CAST IRON (issue #423):** TipForm Cursor overspend (`Get-BobCursorOverageGbp` / `account_overage_gbp`) is **local Spending only** — never digest GET, never `cursor_pools` / seat-cache `overage_label`. Digest may still *publish* `overage_gbp` for peers; this seat must not paint from that. Digest `overage_gbp` may be null while local TipForm has GBP (`box-usage`). A plain `0%` or `82%` label is not overspend.
- Empty auto remaining (0%): then fuel falls through to grok.exe. Sand 100% does not by itself mean auto is empty.
- Machine tile bars still use xAI `unified.jsonl` weekly remaining (`Get-BobWeeklyRemaining`: legacy `creditUsagePercent`, or Grok 1.0.41+ `currentPeriod.end` with `remaining_pct` unknown / `n/a` — FR #427).
- **FR #430:** start gate uses `Get-BobGrokAvailability` when `%` is null — verified local auth + current weekly period ⇒ start without API key; only explicit `remaining_pct=0` is exhaustion (`needs Simon: API key`). Unknown/stale/auth-failed ≠ exhausted.
- Numbers: `box-usage`. Do not invent weekly %.

Fleet peer freshness: `Watch-Bobiverse` polls `!bobiverse` (~120s). Chair
nick is Jeeves (`bob-jeeves-chair`). Chair whispers **`BOB DIGEST v1`**
JSON (`i/n` chunks when large); `Import-BobIrcTrayPull` writes
tray-complete `bob-peers\*.json`, `_report-digest.json`, and cursor pool
cache. HTTP digest GET is the same `reportUrl` (PR #306). Not POINT, not
a presence-only digest.

## Reset countdown (AgentMonitor #148 / FR #445)

Show time until weekly reset next to the meter, not only in digests.
`Format-BobResetLabel` formats from the known `period_end` (no extra polling):

- **No** `Until reset:` prefix. Units: if `days > 0` → `N days, M hours` (omit zero hours; never minutes). If `days = 0` → `N hours, M minutes` (omit zero hours when only minutes remain). Clamp expired/negative to `0 minutes`.
- **Hide when polled since reset:** if usage `FetchedAt` >= `period_end`, omit the reset line (percentage still shown).
- **Each Cursor spending group** (`grok chat`, `high cost models`, `Low cost models`): countdown on that row. `grok chat` uses Sand `nextResetTimestampUtc` (`sand_period_end`) only — never Cursor `billingCycleEnd` (FR #448). The other two use the Cursor Spending billing cycle end. Per-group `period_end` on the seat cache wins for non-Sand groups when present.
- **Each machine tile**: that xAI seat's `currentPeriod.end` from `unified.jsonl` (`Get-BobWeeklyRemaining`). Same-seat machines share one reset instant (and one remaining %).
- Fleet share: IRC POINT still includes `reset=YYYY-MM-DD` for peers.
- Durable cache: `~\.grok\bob-bridge\seat-period-end.json` (by_machine + by_seat). Import must **not** wipe an existing peer `period_end` when an older POINT lacks `reset=`.

Example control headings:

`grok chat  N%  2 days, 4 hours`

`high cost models  N%  2 days, 4 hours`

`Low cost models  N%  3 hours, 15 minutes`

`flamingo  -  Club Madeira (N%) - 2 days, 4 hours`

TipForm layout (Simon 2026-09-23):

- Cursor spending rows are **indented** like machine tiles under Grok accounts.
- Overspend (`overspend` plus GBP amount) is **right-aligned inside the tile host** (not past the tip edge).
- Digest webhook merge `status` is `I am online` (`Build-BobDigestWebhookMergePayload`). Channel talk is the idle/busy line from `Format-BobIrcPeerTalkLine`, not a fixed operational banner.

Job lines under a machine (local jobs or digest `pcent` / task):

`START  SimonBarnett/agentic_irc  <sha>  composer-2.5  report digest  <runtime>`

No `grok.exe ? running` when repo/sha exist on the packet. **Coding jobs**
(`SimonBarnett/...`, sha, fuel) come from the digest webhook
(`config/bobiverse.json` `reportUrl` → `Write-BobIrcStatus` on each box).
When that machine posts `jobs=[]`, `running=0`, `queued=0`, the tile is
`no jobs` even if an old chair row had `repo:irc` / `irc agent` junk. Bare
`repo: irc` is **not** a Copilot/git START line. IRC `bob-*` presence alone
does not invent a fleet coding job. Idle seat with no live worker process:
`no jobs`.

Do not show `Cursor Models (-GBP x.xx)` as the remaining figure. That was
Sand overage mislabelled (20 Sep 2026 tray vs Spending).

## UI hard rules (diagnostics 2026-09-20)

- **Click-only card.** Left-click (or Status menu) opens/parks the dark TipForm via `ShowParkedAt`. **No hover** to show the card (hover caused double TipForm / ghost chips). Close only via **X**. No `hideTip` auto-hide.
- **One TipForm only.** `NotifyIcon.Text` stays blank always (`Clear-BobNativeTip`). Never park `P+ idle` text -- that white chip is the bad second dialog.
- **Single instance.** Mutex `Local\BobFleetTray-<machineId>`. Shortcut target `tools/Start-BobFleetTray.ps1` will not start a second tray (brings forward / tip flag). Ghost trays: kill extras, keep one.
- **No blank card on refresh.** In `Rebuild-BobTrayTiles`:
  1. Resolve/format every label and color **before** `Controls.Clear()`.
  2. Wrap Clear+Add under `SuspendLayout` / `ResumeLayout` only.
  3. **Never** use `WM_SETREDRAW` / `SendMessage(SetRedraw)` on TipForm -- a mid-rebuild error with redraw left off blanks the card forever.
  4. TipForm is double-buffered (`DoubleBuffered` + optimized paint styles).
  5. Overage-red check is **inline** in `Watch-BobTray.ps1` (label starts with `-` or contains a GBP sign). Do not call `Test-BobCursorOverageLabel` from the tray script (may be unloaded).
- **TipForm must compile.** Exactly one `DllImport` for `SendMessage` in the embedded C# TipForm. A duplicate P/Invoke prevents `Add-Type` and kills click/Status (no dialog).
- Icon: Font Awesome Free solid robot. `$notify.Visible = $true` must stay (missing icon = Visible never set / TipForm CreateHandle at startup).
- Do **not** preload `$script:tip.Handle` at startup.
- Footer: `alert: watcher|stall|weekly|none`.
- Log: `~\.grok\long-running-background-tasks\watch_bob_tray.log`.

## Restart watcher (FR #346)

Menu **Restart watcher** runs `tools/Invoke-BobFleetReinstall.ps1` on **this machine only**
(never Ergo / Jeeves / other boxes; never logs secrets):

1. Fast-forward fleet checkouts from `config/bob-fleet-repos.json` (or example); dirty trees get a named stash, never discarded.
2. Idempotent tool/CLI updates; skill book reinstall; deploy scripts + record deploy SHA.
3. Restart ear/watchers/monitors; busy seats are **not** force-killed by default (wait for DONE).
4. Balloon + `tray-reinstall.log` / report JSON with old/new SHAs and failures.
5. Relaunch tray via `Start-BobFleetTray.ps1` (single instance).

**Bob Fleet** Desktop / Start Menu shortcuts (from `Install-BobFleet`) target `Start-BobFleetTray.ps1`.

## Install / recycle

```powershell
powershell -NoProfile -File "$repo\tools\Install-BobFleet.ps1" -MachineId <id> -CwdRoots <roots>
```

Copies `.grok/skills/*/SKILL.md` into `~\.grok\skills` via `Copy-BobProjectSkills`. Creates **Bob Systray** Start Menu + Desktop shortcuts (`tools/Install-BobFleetTrayShortcut.ps1`) with `assets/bob-systray.ico` (same robot as NotifyIcon).

### Bob Systray Start / Restart (CAST IRON — Simon 2026-09-27)

Start Menu / Desktop: **one** shortcut `Bob Systray.lnk` only. Restart is the
systray context-menu **Restart** when the tray is running (same
`Start-BobFleetTray -ForceNew` bootstrap). No separate Restart icon.

`tools/Start-BobFleetTray.ps1` **always**:

1. Runs deterministic `Update-BobSystrayFromGit.ps1` (git fetch + install when
   behind `origin/main`; Updating dialog when work is needed). **No LLM.**
2. **Closes prior agents** via `Stop-BobSystrayPriorAgents.ps1` (Watch-AgentHealth
   seats, `grok.exe` / Grok Bot TUI, cursor-agent). Old agent windows must not
   survive Start/Restart.
3. **Tidies** leftover session `powershell` / `python` / `node` via
   `Cleanup-OrphanAgents.ps1` (keeps live fleet watchers; skill
   `cleanup-orphans`).
4. **Sweeps orphan NotifyIcons** (ghost tray icons) via
   `Clear-BobOrphanNotifyIcons.ps1` (WM_MOUSEMOVE over the notification
   toolbars; does not restart Explorer).
5. Starts / ForceNew-replaces the tray via `_Watch-BobTray-<machineId>.ps1`.

Systray **Restart** = same Start bootstrap (`-ForceNew`). **Exit** writes
`agent.quit.request` then stops the bobiverse ear (IRC logoff).

While running, the tray POSTs local Cursor `pcent` + `overage_gbp` and local
xAI `weekly` via `Write-BobIrcStatus` every **30s** (digest webhook). Unhandled
exceptions open owning-repo GitHub issues via `Report-BobDeterministicException`
(`gh`, no model tokens).

```powershell
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "$repo\tools\Start-BobFleetTray.ps1"
# or: Install-BobFleetTrayShortcut.ps1 -RepoRoot $repo
```

Seat wrapper (generated by `Install-BobFleet`; do not hand-edit, do not paste into this skill): `tools\_Watch-BobTray-<machineId>.ps1`. Ionos: `tools\_Watch-BobTray-ionos.ps1`. It sets `BOB_MACHINE_ID` and the bobiverse IRC home, kills other `Watch-BobTray` processes, then runs `Watch-BobTray.ps1`.

Hover/flash/card/TipForm code changes: recycle **Watch-BobTray only** (or use Restart Bob Systray shortcut so git update runs).

1. Kill **all** `Watch-BobTray` processes (ghosts included).
2. Start **exactly one** via `Start-BobFleetTray.ps1` (preferred) or the seat wrapper.
3. Launch with **CreateNoWindow** (no console) for the tray process. Updating dialog is allowed to be visible while git install runs.
4. Do not `Stop-ScheduledTask BobFleet-*` while build jobs run.
5. Do not recycle `Watch-Bobiverse`, `BobIrcd`, or `BobJeeves` for a tray paint change. IRC recycle is `bob-irc` (Watch-Bobiverse only).

### Durable start (job object / WMI) — CAST IRON 2026-09-30

`Start-Process -PassThru` children stay in the launching console **job object**.
Grok Build / agent shells kill that job when the shell exits, so TipForm can
log `tray up` then vanish. `Start-BobFleetTray.ps1` must start the seat wrapper
via **`Win32_Process.Create`** (WMI breakaway), with `Start-Process` only as
fallback. Agent one-shots: same WMI create; never redirect stdout/stderr of the
tray to the agent shell.

Seat-wrapper peer kill must match **`-File …Watch-BobTray.ps1`** /
**`-File …_Watch-BobTray-*.ps1` only**. A broad `CommandLine -match "Watch-BobTray"`
stops diagnostic shells whose argv merely mentions the path.

On bobiverse installs (`C:\ai\bob`): companion is **`scripts\Start-BobTray.ps1`**
+ HKCU `Run\BobiverseTray` / Startup; **disable** legacy `BobFleet-<id>` tasks.
When **`ircBob` is Running**, `Watch-Bobiverse` must **not** spawn a second
legacy `bob-*` ear.

### PipelineStoppedException / version footer

Call `Application.SetUnhandledExceptionMode(CatchException)` **before** any
WinForms control is created. Swallow `PipelineStoppedException` on timer ticks
and ThreadException (recycle `Stop-Process` mid-tick). TipForm shows product
version bottom-right (`bob {ver}` from `BOBIVERSE_BOB_VERSION` / `VERSION`).

Card place: `Get-BobTrayTipPlacement` (icon rect, then sticky when already visible, else cursor). TipForm uses `ShowWithoutActivation` / WS_EX_NOACTIVATE.

## Diagnose (when the card/icon misbehaves)

1. Count `Watch-BobTray` processes -- more than one: kill all, start one (CreateNoWindow, seat wrapper).
2. Log tail `watch_bob_tray.log` for `tray up`, `tip show ok`, poll errors.
3. Confirm `$notify.Visible` path still sets Visible=$true after start.
4. Confirm `NotifyIcon.Text` is empty (no white P+ chip).
5. Confirm title `#Bobiverse (<id>)`, three Cursor bars (grok chat, high cost models, Low cost models) from **local** Spending when this host has a Cursor login; digest only fills nulls when it does not. Seat labels beside names; shared % on ntsa seats.
6. Bars stuck at `n/a` on MarchHare (no Cursor login): digest GET is not `https://irc.ntsa.uk/bob/v1/report`, or peers omitted `pcent`. Checklist: `bob-digest-webhook`. Do not invent the percent. On ionos/flamingo, `n/a` means local Spending failed — fix local, do not fall back to digest for the pool check.
7. Click / Status does nothing: TipForm C# failed to compile -- check for duplicate `SendMessage` P/Invoke or Add-Type errors in the log.
8. Refresh clears the card: rebuild cleared controls while redraw was suspended, or an exception after Clear -- drop WM_SETREDRAW; format labels before Clear; ResumeLayout + Refresh always.
9. If card flashes on poll: verify SuspendLayout/ResumeLayout wraps `Rebuild-BobTrayTiles` (no SetRedraw).

## Agents menu

The context menu has an **Agents** submenu (the two watch-seat agents as one
menu; select which). TipForm Cursor/Grok section headers are the same links.
Each entry uses a **visible** agent icon (`ExtractAssociatedIcon` plated on a
light chip, else a bright C/G badge). Not installed -> greyed icon, click
**initialises setup** (`tools/Install-AgentMonitor.ps1`); installed -> click
launches `Watch-AgentHealth.ps1 -WatchWorker -Cursor|-Grok **-New**` (always a
fresh session + skills + prompt -- never resume) with **`-Windows on`** so the
agent TUI is visible for humans (never `-Windows off`). Watch host PowerShell
stays Hidden. Cursor also gets `-Model auto`. Owner skill: `agent-monitor-setup`.

### Empty fuel / session API key (Simon 2026-09-24)

Before **Start Agent** or **Plan** start, tray checks fuel: Grok from
`machines.*.remaining_pct` / digest `pcent.grok-chat` (FR #356); **Cursor
auto pool from local Spending** (`Get-BobTrayCursorFuelRemaining` →
`Get-BobCursorAgentWeeklyRemaining`) — never digest for the Cursor pool gate:

- **Remaining > 0 or unknown**: unchanged launch (no dialog).
- **Grok remaining 0**: WinForms password dialog for `XAI_API_KEY`. Cancel aborts.
  OK sets the key only on the child process env (not tray Process, not User/Machine,
  not disk profiles / `auth.json`).
- **Cursor remaining 0**: same dialog for `CURSOR_API_KEY` (`cursor-agent --api-key`
  / env). Cancel aborts. Never persist.

### Plan -> Grok / Cursor (Simon 2026-09-24; fresh folder PR #339)

Top-level **Plan** menu (sibling of **Agents**, not nested under it) -> **Grok** | **Cursor**:

1. Sync https://github.com/SimonBarnett/skills-visionary via
   `tools/Install-VisionarySkills.ps1` (clone/pull sister repo; copy
   `.grok/skills/*/SKILL.md` into `~/.grok/skills`). Visionary pack only —
   do not pull agentic_build skills into the Plan seat.
2. **New empty plan folder every click** (`New-BobTrayPlanWorkspace`):
   `%USERPROFILE%\BobPlans\plan-yyyyMMdd-HHmmss` (suffix `-2`, `-3`… same second).
   Fresh skill book via `git archive` (no leftover plans from the shared clone).
   Previous BobPlans folders are never deleted.
3. **No IRC / no build**: does **not** launch `Watch-AgentHealth`, does not join
   shop channels, does not start Watch-Bobiverse / bob ear.
4. **Plan mode**: Grok `agent.exe --permission-mode plan --session-id <new GUID>
   --cwd <BobPlans folder>`; Cursor `agent.cmd --plan --model auto --workspace
   <BobPlans folder>`. Never `-r` / `--resume` / `-c` / `--continue`. Visible TUI.
5. Reuses the same empty-fuel session API key dialogs as Start Agent.
   Test: `tests/BT0plan-new-session.ps1`.

### Agent shortcut icons (CAST IRON -- Simon 2026-09-23)

Tray Agents / TipForm icons must match the Desktop agent shortcuts. Resolver
order in `Watch-BobTray.ps1` (`Resolve-BobTrayAgentIconExe` /
`Resolve-BobTrayDesktopShortcutExe` / `Get-BobTrayAgentExeCandidates`):

1. **Desktop / Public Desktop `.lnk`** -- `Cursor.lnk`, `Grok Bot.lnk` (also `Grok.lnk`). Prefer `IconLocation` (path before comma); if empty, use `TargetPath`. Cursor Desktop `.lnk` often has empty IconLocation; TargetPath to `%LOCALAPPDATA%\Programs\cursor\Cursor.exe` is enough for `ExtractAssociatedIcon`.
2. **Grok Bot branded exe** (before CLI `grok.exe`):
   - `%ProgramFiles%\Grok Bot\Grok Bot.exe` (common on ionos / fleet MSI)
   - `%ProgramFiles(x86)%\Grok Bot\Grok Bot.exe`
   - `%LOCALAPPDATA%\Programs\Grok Bot\Grok Bot.exe`
3. **Cursor exe**: `%LOCALAPPDATA%\Programs\cursor\Cursor.exe` (and `Programs\Cursor\`, `%ProgramFiles%\Cursor\`).
4. Badge fallback only when no exe exists (bright C / G chip).

Do **not** resolve Grok icons only under LocalAppData -- that misses Program
Files installs and leaves the Agents menu without a real icon. After changing
resolver paths, recycle the tray (kill all Watch-BobTray, one CreateNoWindow
start) so the menu rebuilds. `Install-AgentMonitor` refreshes Desktop `.lnk`
IconLocation via AgentMonitor `Publish-DesktopShortcuts.ps1`.

## Hard rules

- Not a Windows service.
- Do not print auth.json or tokens.
- Do not invent weekly %. No billing HTTP scrape.
- Do not report session context as weekly quota.
- Job lines are GitHub owner/repo, never a commit SHA as primary label.
- Do not omit registered bobiverse seats. Do not invent jobs. Do not WinRM.
- CAST IRON: Cursor pool remaining / Agents fuel gate = local Spending. Digest fills nulls only; never overwrites local.

### Exit / Restart IRC (agentic_irc #250 / FR #453)

`Exit` and `Restart` on the systray menu announce via `bob-{machine}` on
`#bobiverse` (`tray Exit|Restart - logging off IRC`). Ordering CAST IRON:

1. Archive any stale `outbox.txt` backlog, write **only** the departure PRIVMSG.
2. Wait until irc_agent drains that line (outbox empty / marker absent).
3. Write `agent.quit.request`, wait for bobiverse `irc_agent` to stop.
4. Then `Stop-BobiverseMoot` (force leftovers). Never kill before announce flush.

`Restart` then relaunches via `Start-BobFleetTray -ForceNew` (same bootstrap as
Start). External `-ForceNew` also best-effort announces if no prior logout line.


### Recycle Bob (agentic_build #442)

`!recycle` / bob_recycle must announce departure (`bob-{machine}: recycling … logging off IRC then restarting Watch-Bobiverse + TipForm tray`) then restart TipForm via `Start-BobFleetTray -ForceNew` — the same bootstrap as systray Restart — not a raw `Watch-BobTray.ps1` spawn.


### TipForm pools / countdown (FR #445 / #448)

- **grok chat** bar = Cursor Sand only (`sand_remaining_pct` / `cursor_spending_groups[id=grok-chat]`). Never copy auto / high-cost.
- **grok chat** reset = Sand weekly (`sand_period_end` / `nextResetTimestampUtc`) only. Never fall back to Cursor `billingCycleEnd` / `period_end` (FR #448).
- TipForm label for wire id `auto` is **Low cost models** (id stays `auto`).
- Reset countdown has **no** `Until reset:` prefix. `days > 0` → `N days, M hours`; `days = 0` → `N hours, M minutes`.
- Local Bob publishes only its own pools (`Get-BobCursorPoolsForTray -LocalOnly` on Write-BobIrcStatus).


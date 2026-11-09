# bob tray dialogs and layout (t828u / t829u)

## Where the systray and the agent watcher live (t829u)
The systray (`Watch-BobTray.ps1`, BobBridge module, tools, assets, config) and the agent watcher (`Watch-AgentHealth`) belong to the
ircBob service, so they are **first-class bob sources**, not vendored third-party code:

| Source (git) | Flat staged / installed spelling |
| --- | --- |
| `bob/tray/{tools,src,assets,config,dialogs}` | `<root>\tools`, `src`, `assets`, `config`, `dialogs` |
| `bob/agentwatcher` | `<root>\Watch-AgentHealth` |

Staged and installed trees stay flat. The old spellings (`third_party\bob-tray`, `third_party\Watch-AgentHealth`) still resolve through
`Get-BobiverseRepoPath` / `repo_layout.py`. `Sync-BobTrayFromAgenticBuild.ps1` is retired (needs `-AllowRevendor`): edit the sources in place.

## Compiled dialogs (t828u)
`Acknowledge` and `Status` are small native exes, `tools\bob-about.exe` and `tools\bob-status.exe`; since t832u the systray itself is a third one, `tools\bob-tray.exe`, which hosts both windows in-process.

* **Tech: C# WinForms, compiled by the in-box .NET Framework 4 `csc.exe`** (`scripts\Build-BobDialogs.ps1`, sources `dialogs\*.cs`).
  Why: ~26 KB exes, nothing to unpack at start (a PyInstaller one-file exe extracts ~10 MB to `%TEMP%` on **every** start and tkinter adds
  more), only NGEN'd framework DLLs, no extra toolchain on the build or target machine (csc ships with Windows 10/11).
* **About**: ntsa badge (embedded), "by Simon Barnett", `bob <version>  machine: <id>`, then one block per install of bob / jeeves / airc / ergo
  (version, BUILD.json date, commit, path, service state - the same text as the old `Format-BobInstallInfo`). The window opens first; the install
  scan (services, BUILD.json, git only when BUILD.json has no commit) runs on a worker thread and fills the box.
* **Status** (FR #4938 / #5179 / #6214 / #6285): one **xAI weekly** capacity heading (digest `machines.<m>.xai_weekly` only; Cursor not mixed into this title); Grok account rows (one grok/cursor account per machine; Cursor spending-group bars removed), each machine's
  workers as `{irc nick}: {doing|idle}` from the digest, `alert: <kind>`, version footer. It paints from `<root>\run\tray-status.json`, which
  the tray writes (atomically) after every poll; the exe never touches the network and re-reads the file every 2 s. Parked until X / Esc; drag by the title.
  One account-wide Copilot tile uses `copilot_pool` / `copilot_line` from the snapshot, showing `unknown` when absent and
  `unlimited` when reported as such (never as zero/exhausted). Live values require the #5173 `bobreport.py` deployment on
  the digest host (`https://bob.ntsa.uk/bob/v1/report`); that deployment is separate and needs Simon's go.
* **Single instance**: a named mutex per dialog; a second launch only brings the first window forward and exits.
* **Tray**: `Start-BobTrayDialog` (`tools\BobTrayDialogs.ps1`) is a plain `Start-Process` - the tray UI thread never waits on a dialog or on the
  install scan (the old in-process About blocked it for seconds). If an exe is missing the tray falls back to the old PowerShell dialogs.
* **Packaging**: `Pack-BobiverseRelease.ps1` builds the exes into `stage\tools` (and ships `dialogs\`); `Sync-BobiverseFromRepo.ps1` mirrors
  `dialogs\` and compiles into `<install>\tools` when an exe is missing or older than its sources (a running dialog is replaced by rename);
  `Install-Bob.ps1` builds them on a repo install.
* **Switches** (support/tests): `bob-about.exe --text-out f` (headless install text), `bob-status.exe --check snapshot.json --text-out f`,
  both `--png-out f` (render and exit) and `--timing-out f` (ms from process start to the first shown window), `--root <install root>`.

## Compiled systray (t832u)
The PowerShell tray was slow to start and slow to open its menu, so **`tools\bob-tray.exe`** (same C# / csc.exe tech, ~50 KB, same build script)
now owns everything the user touches: the notify icon and its robot images (idle, alert A/B, context), the right-click menu (native menu handle
pre-created, so the first right-click is as fast as the tenth), click / double-click handling, the flashing, and the hover text.
It runs the Status and About windows in-process (no second process to start).

* **Menu**: **Status** (bold, the default), **Agents** (Automatic, Grok, Cursor, OpenCode), **Plan**, Acknowledge, Open log, separator, Restart, Reload engine (FR #5111), Exit. Left click = acknowledge + Status;
  double click = Status. Agents does not call `bob-worker --list-agents` while the icon is created. Opening the submenu asks `bob-worker.exe --list-agents` on a background thread. A fresh fuel cache is shown as known. A missing or slow reading stays clickable as fuel unknown, not as exhaustion, and one `--refresh-fuel` pass then updates the rows. A second open while that pass is running does not start another child. An older worker without `--list-agents` leaves the explicit rows disabled. Launch still reads fuel and refuses a real miss. It does not substitute another agent.
* **Agents / Plan** are native (`BobTray.cs` `WorkerLauncher.Launch`). Plan stays one click with no `--agent`. Automatic omits `--agent`. Grok, Cursor, and OpenCode pass `--agent` and the worker refuses instead of starting a different agent. The 2-worker cap is the **union** of IRC agent seat marker pids (live) and live agent `bob-worker` roots (FR #3181 / FR #4307 / MRB #4311). The worker exe runs from the sha256
  run-copy under `%LOCALAPPDATA%\Bobiverse\worker\bin`, and it opens its own console window (same rules as the PowerShell launcher). Rebuild `bob-tray.exe` and `bob-worker.exe` together (`scripts\Build-BobDialogs.ps1`, `scripts\Build-BobWorker.ps1`). Keep `scripts\opencode_fuel.py` on the install.
* **The engine** - the data collection (digest, Grok / Cursor pools, alerts, BobBridge) is still PowerShell. `bob-tray.exe` starts
  `tools\_Watch-BobTray-<machine>.ps1` hidden with `BOB_TRAY_ENGINE=1` and `BOB_TRAY_EXE_PID`; in that mode the script never shows an icon.
  Exe and engine talk only through files in `<root>\run`: `tray-status.json` (engine -> exe: `short` hover text, `alert`, `attention`,
  `attention_seq`, `pulse`, plus the dashboard model), `tray-env.json` (engine -> exe: the `BOB_*`/`AGENTIC_*`/`BOBIVERSE_*` environment for workers),
  `tray-cmd.txt` (exe -> engine: `ack`, `exit`, `restart`; operator/ear -> host: `reload` FR #5111). The engine leaves when the exe is gone; the exe restarts a dead engine (max 3 per 5 min).
* **Exit** closes the windows, hides the icon, stops the ircBob service (detached) and ends the engine; **Restart** hides the icon and has the engine
  re-launch the tray **without** restarting ircBob (FR #5111 `-SkipServiceRestart`). `Start-BobFleetTray.ps1` launches `bob-tray.exe` when it exists (ForceNew, tidy unchanged; ircBob restart-on-start only when not skipped) and
  kills the old PowerShell tray; without the exe it starts the PowerShell tray as before, which stays a complete fallback.
  Restart allows up to 60 seconds for the graceful IRC logout and bootstrap (FR #5177). Commands are claimed before callbacks,
  and engine startup discards stale commands so an interrupted restart cannot replay.
* **Reload engine** (FR #5111): host-only recycle. Write `reload` to `<root>\run\tray-cmd.txt` (or menu **Reload engine**). The elevated `bob-tray.exe` runs `KillEngineTree` + `StartEngine` only --- no `taskkill` from Medium integrity, no host exit, no seat kill, no `sc stop ircBob`. Engine must leave `reload` lines for the host.

## Hot-patch the tray (FR #5111)

1. Stage patched files into the live install (`bob\tray\tools\Watch-BobTray.ps1`, helpers; rebuild `bob-tray.exe` only if the C# host changed: `scripts\Build-BobDialogs.ps1`).
2. Write `reload` (one line) to `<install>\run\tray-cmd.txt`, or use TipForm **Reload engine**.
3. Verify one `powershell.exe` engine under one `bob-tray.exe` host (`BOB_TRAY_ENGINE=1`). ircBob / seat pids stay put.
4. Confirm digest / `engine.alive` ticks after the new engine start.
* **Single instance**: a named mutex per normalized install root (FR #2585: trim quotes/trailing slash + `GetFullPath` so argv variants share one mutex). A second `bob-tray.exe` logs `process-exit reason=already-running` (never `unexpected`) and does not write `tray-up`.
* **Switches** (tests): `--root`, `--machine`, `--no-engine`, `--dump-menu f`, `--dump-state f --text-out f`, `--seats --text-out f`, `--timing-out f`
  (ms to icon visible, ms to the menu's Opened event).

### Status window shows the dashboard only (t832u)
The plain-text block under the title (the old hover / tooltip `jobs_text`: fuel lines, "GitHub issue post: ready", "out of tokens, open with key")
was drawn by mistake. It is gone from the exe and from the snapshot (`jobs_text` is no longer written): per-machine Grok pool
rows with workers `{irc nick}: {doing|idle}`, one Copilot pool tile, alert and version (FR #4938: no Cursor pool section; FR #5032: no
"Grok accounts" heading).

**Digest-only fleet Cursor/xAI weekly (FR #6267, partly superseded by FR #6285).** When a public digest is present, **peer** machine rows take remaining % only from that machine's digest record. Peer peek, peCache, and seat-min sharing must not paint a non-digest value (class of MarchHare showing `ntsa (43%)` while digest was 74%). Account label prefers digest `cursor_pools.account` (or `nick`) over hardcoded `bob-seats.json` labels such as `ntsa`. Missing digest weekly on a peer paints unknown — never silent local/bridge fallback and never unknown-as-zero. Offline pin: `bob/tests/test_fr6267_tray_digest_only_weekly.py`.

**FR #6285 (supersedes FR #6267 local-row guidance for xAI weekly display):** every TipForm/Status **xAI weekly** row (including this host) is painted only from digest `machines.<m>.xai_weekly` (`remaining_pct`, `fresh`/`age_s`/`error`, `period_end`, `account`). Never local `unified.jsonl` / `Get-BobWeeklyRemaining` for display — with or without a digest. Null meter or no digest => clear `no reading`. Section heading is exactly **xAI weekly** (never Cursor AccountLabel/AccountName). Local weekly may still feed worker fuel selection and seat period cache; it must not paint TipForm/Status rows.

**FR #6285 CI (`build-bob-tray.yml`):** GitHub Actions on `windows-latest` compiles `bob-tray.exe` / `bob-status.exe` / `bob-about.exe` via `bob/scripts/Build-BobDialogs.ps1` whenever `bob/tray/**`, `bob/scripts/Build-BobDialogs.ps1`, `.github/workflows/build-bob-tray.yml`, or `bob/tests/test_fr6285_tray_build_ci.py` changes (plus `workflow_dispatch`). The job uploads the three exes plus `*.sha256` and `provenance.txt` (workflow commit + SHA-256). A smoke check fails if the PE lacks UTF-16LE `xAI weekly` or still embeds `Cursor / xAI weekly` (throw text includes `missing UTF-16LE heading` / `still embeds stale heading`). Source-only merges do not update a live `tools\bob-tray.exe`; Slab (or Pack/Sync) must deploy a built artifact / rebuild locally after C# heading changes.



## Copilot freshness (FR #6148) + historical-max % (FR #6215)

- `Format-BobCopilotPoolLine` / `Get-BobCopilotFreshness` treat `fetched_at` older than **900 seconds** (or missing/unparseable/far-future) as stale.
- A future `resume_at` (dispatch cooldown) does **not** force fresh: age is always from `fetched_at`.
- Stale paint: `Copilot - <value> [stale <age>]` (or `[stale]`). Stale is a text marker only --- TipForm/Status do **not** paint Copilot red or right-align the meter (FR #6317).
- **FR #6215:** known `reset_at` still paints a countdown using the same `Format-BobResetLabel` convention as other pools (even when stale). Past/missing reset stays omitted.
- **FR #6215:** when `used` and `max_recorded_usage` are known, remaining % is derived from historical max (high-water mark bumped when usage exceeds it --- **not** a contractual quota). Missing/zero denominator paints `unknown`.
- Snapshot fields: `copilot_line`, `copilot_stale_line`, `copilot_fresh_until` (unix seconds), `copilot_bar` (`known`/`pct`/`r`/`g`/`b`), plus digest `max_recorded_usage`. Native Status re-ages an open window at the deadline without waiting for a new poll.
- TipForm always shows a Copilot line (`Copilot - unknown` when absent). Display-only: does not enable Copilot dispatch (`BOB_FUEL_COPILOT` / #6204).

## FR #6301 tray fuel rows and agent starts

OpenCode Go window lines and the Copilot meter use remaining percent: `<title> - <x>% left - <reset>` (OpenCode: `go <window> - <x>% left - <reset>`). Bars paint remaining % green to red. Copilot title is exactly `Copilot` (no included-unlimited prose). 100% used / exhausted paints `0% left`. Unlimited Copilot without a historical max paints `unknown`. Reset labels come from real digest/API data (`Nd Hh` above 24h, else `Hh Mm`); never invent rem-est text.

## FR #6317 Copilot layout like OpenCode rows

TipForm and Status paint Copilot as a family header plus one left-aligned UsageRow `Copilot - <current text>` with a remaining-% bar (green-to-red; `0% left` => empty fill; unknown => neutral empty track). Never put the meter on section RightText and never colour the Copilot block red for stale. `Get-BobCopilotMeterBarPct` keeps the remaining % when stale so the bar still draws. Live MarchHare hover screenshot remains Slab.

**Digest-only OpenCode paint:** `Get-BobTrayHover` must not read or overlay `run\opencode-fuel.json` for Status/hover. Digest-known `opencode_windows` always win. When every window error is `no key set`, show that instead of n/a.

**Agent starts:** Agents menu entries (Automatic / Grok / Cursor / OpenCode) carry no fuel or quota reason text. OpenCode model submenu is omitted (OpenCode has `/model`); `bob-worker` sets `BOB_OPENCODE_MODEL` from `opencode_default_model`.

**Labelled OpenCode keys (Part D):** ear reads `config\opencode-keys\<label>.apikey` (SYSTEM+Administrators ACL) via `Write-BobOpencodeGoApiKey.ps1` or hand-copy; publishes `opencode_account` and `no key set` when absent. TipForm masked set/select menu lands in FR #6309.

Offline pins: `bob/tests/test_fr6301_tray_fuel_agent_starts.py`, `common/tests/test_fr6301_opencode_keys.py`, `bob/tests/test_mrb6303_docs_pins.py`.

## FR #6309 TipForm OpenCode keys menu

Context menu **OpenCode keys** offers Set key (masked PasswordChar dialog), select among `config\opencode-keys\*.apikey` labels, and Remove key. Writes use SYSTEM+Administrators ACL (same as `Write-BobOpencodeGoApiKey.ps1`). Headless test flags: `--opencode-key-write|--opencode-key-select|--opencode-key-remove`. Removing the last key clears digest `opencode_account` via fuel merge `cleared[]`.

## OpenCode windows (FR #6147)

Status snapshot carries `opencode_line`, `opencode_window_lines` and `opencode_bars` for **free** plus Go **rolling / weekly / monthly**. A digest with `opencode_windows=null` (the MarchHare card that showed only `[OC] OpenCode n/a`) still writes those four rows. Unknown bars are empty tracks (`known=false`); they are never filled as 100%. Stale clears the painted percent. Unstarted rolling (`Starts on first use`, no reset) is only used after a completed stats read. A missing helper result stays `unknown`.

There is no OpenCode remaining-quota API. Free percent is 100 only when `opencode models` lists an uncapped free model; otherwise free stays null. Weekly and monthly percents are local `opencode stats --models --days 7|30` cost versus the hardcoded caps, not a provider balance. The 5-hour rolling window and any reset countdown are **not** in `opencode stats`. Reset text is shown only when a record already has `reset_label`.

The ear must not wait on the helper: `Get-BobOpencodeFuel.ps1` runs three `opencode` calls (up to 25s each). `bobreport.py` starts it in the background and polls. A 120s deadline stops that powershell **and its opencode children** (`taskkill /T`), not the parent alone.

`free catalogue` means `opencode models` listed an uncapped free model. It is not a remaining-quota bar. Per-model `7d local $` amounts are `opencode stats --models` cost for the process that ran the CLI, not a provider balance. A service-identity stats table with 0 sessions, 0 messages and no model rows is empty local history: windows stay `unknown`, not `unstarted`, and that document must not replace a cache that already has user sessions or `local_costs`. Rolling with no 5-hour sample is `not measured` (no `0% used`). A fresh local cache is not blanked by a stale digest flag. Cost-versus-cap percents that are still shown are labelled `est`.

**Frozen ear bootstrap.** Allowlisted overlays from `scripts\` are `bobreport` (marker `opencode_install_root`) and `opencode_fuel` (marker `GO_ZEN_USAGE_USER_AGENT`, FR #6263). Every other ear import, including `gitclaim`, comes from the exe embed. An old `scripts\gitclaim.py` is left in place and is not imported. Do not delete scripts to force the embed, and do not copy the rest of `scripts\` over the embed.

**Go zen acquisition (FR #6263).** Service-owned fetch uses User-Agent `Bobiverse-bobreport/1.0` (same class as digest FR #6144). Key from `BOB_OPENCODE_GO_API_KEY` or `<InstallRoot>\config\opencode-go.apikey`. Publish diag includes `opencode_acquisition=` / `opencode_source=` (kinds: json, auth_error, entitlement_error, blocked_1010, rate_limited, unavailable, missing_key). Unknown windows stay unknown. Slab-only live verify after merge.

**OpenCode windows on public digest (FR #6265).** Emitter retention of `opencode_windows` with HTTP 204 is not enough: the hub must run a `jeeves.exe` / bobreport built from FR #6147 (`a40d3bbe`) or later so `opencode_windows` is in `_MERGE_PEER_FIELDS` and tray export. Artifact `5f0ac20a` (PR #6212) keeps `pcent.opencode-go` and drops windows. Offline pin: `common/tests/test_fr6265_opencode_windows_full_chain.py`. Slab owns hub rebuild/deploy and live three-window tray verify; null emitter `reset_label` must stay null.

Install the rebuilt `scripts\bob-ear.exe`, pinned `scripts\bobreport.py` (this head), `tools\Get-BobOpencodeFuel.ps1`, and `scripts\opencode_fuel.py`. If the on-disk `bobreport.py` is an older file without `opencode_install_root`, the embed publisher is used and the old file stays. Cache is `<BOB_INSTALL_ROOT>\run\opencode-fuel.json`. Tray sources at `014b9af` are unchanged. The reader call tolerates a `gitclaim` that has no `shop_line_resets_bored_clock`.

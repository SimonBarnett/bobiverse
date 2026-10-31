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
* **Status** (FR #4938 / #5179): Grok account rows (one grok/cursor account per machine; Cursor spending-group bars removed), each machine's
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

* **Menu**: **Status** (bold, the default), Agent, Plan, Acknowledge, Open log, separator, Restart, Reload engine (FR #5111), Exit. Left click = acknowledge + Status;
  double click = Status.
* **Agent / Plan** are native: the 2-worker cap is the **union** of IRC agent seat marker pids (live) and live agent `bob-worker` roots (FR #3181 / FR #4307 / MRB #4311), the worker exe is run from the sha256
  run-copy under `%LOCALAPPDATA%\Bobiverse\worker\bin`, and it opens its own console window (same rules as the PowerShell launcher).
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

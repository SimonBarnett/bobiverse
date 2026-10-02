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
`Acknowledge` and `Status` are two small native exes, `tools\bob-about.exe` and `tools\bob-status.exe`.

* **Tech: C# WinForms, compiled by the in-box .NET Framework 4 `csc.exe`** (`scripts\Build-BobDialogs.ps1`, sources `dialogs\*.cs`).
  Why: ~26 KB exes, nothing to unpack at start (a PyInstaller one-file exe extracts ~10 MB to `%TEMP%` on **every** start and tkinter adds
  more), only NGEN'd framework DLLs, no extra toolchain on the build or target machine (csc ships with Windows 10/11).
* **About**: ntsa badge (embedded), "by Simon Barnett", `bob <version>  machine: <id>`, then one block per install of bob / jeeves / airc / ergo
  (version, BUILD.json date, commit, path, service state - the same text as the old `Format-BobInstallInfo`). The window opens first; the install
  scan (services, BUILD.json, git only when BUILD.json has no commit) runs on a worker thread and fills the box.
* **Status**: Cursor pools first (fleet), Grok account rows, each machine's workers as `{irc nick}: {doing|idle}` from the digest, `alert: <kind>`,
  version footer. It paints from `<root>\run\tray-status.json`, which the tray writes (atomically) after every poll; the exe never touches the
  network and re-reads the file every 2 s. Parked until X / Esc; drag by the title.
* **Single instance**: a named mutex per dialog; a second launch only brings the first window forward and exits.
* **Tray**: `Start-BobTrayDialog` (`tools\BobTrayDialogs.ps1`) is a plain `Start-Process` - the tray UI thread never waits on a dialog or on the
  install scan (the old in-process About blocked it for seconds). If an exe is missing the tray falls back to the old PowerShell dialogs.
* **Packaging**: `Pack-BobiverseRelease.ps1` builds the exes into `stage\tools` (and ships `dialogs\`); `Sync-BobiverseFromRepo.ps1` mirrors
  `dialogs\` and compiles into `<install>\tools` when an exe is missing or older than its sources (a running dialog is replaced by rename);
  `Install-Bob.ps1` builds them on a repo install.
* **Switches** (support/tests): `bob-about.exe --text-out f` (headless install text), `bob-status.exe --check snapshot.json --text-out f`,
  both `--png-out f` (render and exit) and `--timing-out f` (ms from process start to the first shown window), `--root <install root>`.
# bobiverse

Fleet IRC product: single-file MSIs for **Jeeves** (Ergo + chair), **Bob** ears, and **airc** consoles.

| MSI | Service(s) | Nick | Install tree |
|-----|------------|------|--------------|
| `jeeves-*.msi` | `BobIrcd` + `ircJeeves` | `Jeeves` | `<ai root>\jeeves` (+ Ergo → `<ai root>\ergo`) |
| `bob-*.msi` | `ircBob` (+ tray / Watch-AgentHealth) | `Bob-{machinename}` | `<ai root>\bob` |
| `airc-*.msi` | `Airc` | `{machinename}_console` | `<ai root>\airc` |

## Repository layout

The repo is split per service; each folder holds that service's scripts, skills, agent layer, docs and tests.

```text
jeeves/   scripts/ (Install-Jeeves, Start-Jeeves, Install-BobIrcd/Chair/Webhooks, Watch-*) .grok/skills/ AGENTS.md docs/ tools/ tests/
bob/      scripts/ (Install-Bob, Start-Bob*, bob_worker.py, Build-BobWorker) .grok/skills/ AGENTS.md agents/{worker,plan}/ docs/
          third_party/{bob-tray,Watch-AgentHealth}/ tests/
airc/     scripts/ (Install-Airc*, Start-AircConsole*, airc_console*.py) .grok/skills/ AGENTS.md docs/ packaging/Product.wxs tests/
common/   scripts/ (Bobiverse-Common, Pack-BobiverseRelease, Fetch-*, Update/Sync/Check, the shared python engine: irc_agent.py wire.py ...)
          .grok/skills/ (harvest, fleet-ops) docs/ third_party/{nssm,ergo,wix}/ VERSION tests/ (+ repo_layout.py)
config/ dist/   not tracked (gitignored secrets / build output)
```

The **staged and installed trees stay flat** (`<root>\scripts`, `<root>\.grok\skills`, `<root>\docs`, `VERSION`): `Pack-BobiverseRelease.ps1`
composes `stage\scripts` from all four `*/scripts` dirs, so installers, NSSM services, the updater and the MSIs are unchanged. The python modules
form one import graph (`irc_agent` imports the chair/shop/talk modules), so they live together in `common/scripts`.
Dev: run `pytest` from the repo root (`conftest.py` puts every `*/scripts` on `sys.path`); build a runnable flat tree with
`common\scripts\Pack-BobiverseRelease.ps1 -Product bob -SkipMsi -KeepStage -SkipWorkerExe` and run the installer from `<stage>\scripts`.
Heads-up: an install that still has the pre-split `Sync-BobiverseFromRepo.ps1` finds no `scripts\` in a split clone and syncs nothing until it has
taken the next MSI release.

## The `<drive>:\ai` root (no hard-coded `C:\ai`)

Fleet trees live under `<drive>:\ai` (`<ai root>\bob`, `\jeeves`, `\airc`, `\ergo`, `\bobiverse` clone) but the drive is **not always C:** (MarchHare keeps repos and agent homes on `D:\ai`). Every installer, MSI, updater, Start/Restart script, tray and the worker exe resolve the root the same way:

1. env `BOB_AI_ROOT` (explicit override; MSI: `msiexec /i x.msi AIROOT=D:\ai`),
2. otherwise scan the **fixed physical disks only** (`Win32_LogicalDisk` DriveType 3; removable, network and CD/DVD are ignored) for an existing `\ai` folder,
3. several found: prefer the one already holding `bob`/`jeeves`/`airc`/`ergo` install folders, then the one the fleet services (`ircBob`, `ircJeeves`, `BobIrcd`, `Airc`) already point at, then the system drive, then drive-letter order,
4. none found: `<SystemDrive>:\ai`, created **only** by an installer (never when an `ai` folder exists on any fixed disk).

Implementations (same rules, tested together in `common/tests/test_ai_root_020.py`): `Get-BobiverseAiRoot` / `Get-BobiverseProductRoot` in `common/scripts/Bobiverse-Common.ps1`, `common/scripts/ai_root.py` (worker exe, `gh_filer.py`), `common/packaging/FindAiRoot.js` (MSI immediate custom action: sets `AIROOT`, `INSTALLDIR=[AIROOT]\<product>`, and passes `-InstallRoot` to the post-install script). Scripts that run from an installed tree also use their own location (`<install>\scripts`) before scanning.
## Pack

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File common\scripts\Pack-BobiverseRelease.ps1 -Product all
```

## Install (elevated / UAC)

```bat
bob\scripts\Install-Bob.cmd -MachineId marchhare
jeeves\scripts\Install-Jeeves.cmd
airc\scripts\Install-Airc.cmd -MachineId marchhare
```

Or `msiexec /i bob-0.1.1.msi`.

## Behaviour

- `!register <machine>` (Jeeves, Simon/operators) → ChanServ REGISTER
- Registered `Bob-*` gets +o on shop, +h on `#bobiverse`
- Systray/shortcut Restart → departure announce → `Restart-Service ircBob`
- `!recycle` / `!recycle {mid}` on Bob; `!recycle jeeves` on chair (ircJeeves only)
- Service start self-updates to the latest GitHub release (`Update-BobiverseService.ps1`, v0.1.17): token-less check, detached helper downloads + sha256-verifies the MSI, backs up, installs, rolls back on failure, logs to `%ProgramData%\bobiverse\update\<product>\update.log`. Opt out with `BOB_AUTOUPDATE=0` (or `BOBIVERSE_NO_UPDATE=1`, or a `config\autoupdate.disabled` file). Never touches Ergo or seats; always starts the installed version if the check fails.
- ObjectName = fleet user (DPAPI): interactive prompt, `BOBIVERSE_SERVICE_PASSWORD`, `config\service.password`, or **Complete bobiverse service logon**
- Ergo server PASS is **not** in public MSIs (issue #4); place `config\ergo.password` post-install (or pack with `-EmbedErgoPassword` for private builds)
- Bob ear loads `home\nickserv.password` for SASL (`bob-{machine}`) so reserved nicks get `001`
- Quiet MSI `/qn` never prompts for ObjectName password (issue #6); LocalSystem omits `-BobHome` (issue #7)
- First Ergo install seeds `<ai root>\ergo\ircd.yaml` from `default.yaml` until operator TLS/PASS/ChanServ are set

## Post-install

See **[docs/post-install.md](docs/post-install.md)** (ObjectName password, Ergo PASS, NickServ SASL, verify ear/airc).

Repo: https://github.com/SimonBarnett/bobiverse

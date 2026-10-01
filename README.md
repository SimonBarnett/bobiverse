# bobiverse

Fleet IRC product: single-file MSIs for **Jeeves** (Ergo + chair), **Bob** ears, and **airc** consoles.

| MSI | Service(s) | Nick | Install tree |
|-----|------------|------|--------------|
| `jeeves-*.msi` | `BobIrcd` + `ircJeeves` | `Jeeves` | `C:\ai\jeeves` (+ Ergo → `C:\ai\ergo`) |
| `bob-*.msi` | `ircBob` (+ tray / Watch-AgentHealth) | `Bob-{machinename}` | `C:\ai\bob` |
| `airc-*.msi` | `Airc` | `{machinename}_console` | `C:\ai\airc` |

## Pack

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Pack-BobiverseRelease.ps1 -Product all
```

## Install (elevated / UAC)

```bat
scripts\Install-Bob.cmd -MachineId marchhare
scripts\Install-Jeeves.cmd
scripts\Install-Airc.cmd -MachineId marchhare
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
- First Ergo install seeds `C:\ai\ergo\ircd.yaml` from `default.yaml` until operator TLS/PASS/ChanServ are set

## Post-install

See **[docs/post-install.md](docs/post-install.md)** (ObjectName password, Ergo PASS, NickServ SASL, verify ear/airc).

Repo: https://github.com/SimonBarnett/bobiverse

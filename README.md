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
- Service start runs Release MSI self-update (`Check-BobiverseUpdate.ps1`)
- Jeeves ObjectName = install user (DPAPI): pass `-PromptServicePassword` or set `BOBIVERSE_SERVICE_PASSWORD`
- First Ergo install seeds `C:\ai\ergo\ircd.yaml` from `default.yaml` until operator TLS/PASS/ChanServ are set

Repo: https://github.com/SimonBarnett/bobiverse

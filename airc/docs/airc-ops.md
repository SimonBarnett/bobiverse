# Airc ops (console)

Service **Airc**, tree `<ai root>\airc`, nick **`{MachineId}_console`**.
Canonical **MachineId** is the lowercase sanitized fleet id (`BOB_MACHINE_ID` / `-MachineId`), not a raw Windows `COMPUTERNAME` unless they match.

## ConsoleHome (identity)

| Account | Preferred ConsoleHome |
|---------|------------------------|
| Interactive user | `%USERPROFILE%\.airc` |
| LocalSystem / quiet MSI | `C:\Users\Administrator\.airc` if present, else `<ai root>\airc\home` |
| **Upgrade / reinstall** (FR #1552) | **Existing NSSM `Airc` AppParameters** (PowerShell `-ConsoleHome` / `-MachineId` / … or airc.exe `--home` / `--machine` / `--password-file` / `--operators-file`) |

## airc.exe (FR #2397)

`Pack-BobiverseRelease -Product airc` runs `airc/scripts/Build-Airc.ps1` (PyInstaller one-file) and stages `airc\airc.exe` in the MSI. `Install-AircConsole` prefers that exe as NSSM `Application` with argparse AppParameters; when the exe is missing it keeps the legacy `powershell.exe` + `Start-AircConsole.ps1` path. Smoke: `airc.exe --selftest` and `airc.exe --help`. Target boxes do not need system Python for the console service once the exe is installed.

**Never** default to the invoking user's profile when the `Airc` service is already registered — that resets identity and causes SASL 904 / NickServ 433.
**Never** invent a fresh ConsoleHome on MSI upgrade when AppParameters already name one (including a deliberate `Default\.airc` fleet bake).
`Install-Airc.ps1` / `Install-AircConsole.ps1` read `HKLM\...\Services\Airc\Parameters\AppParameters` first; they also write `<ai root>\airc\config\airc-install.json` (paths only, no secrets) and **read that json as fallback** when AppParameters are missing (service already removed).
Fresh installs still migrate legacy `.airc-console` / Default homes when no prior service / json exists.

## Shop vs #wonderland (FR #3834)

- If ChanServ reports `#{MachineId}` registered -> JOIN shop as `{MachineId}_console` (`reason=registered-machine`).
- Else JOIN `#wonderland` as `{MachineId}_console` (`reason=wonderland-fallback`). Never join `#{domain|workgroup}`.
- Probe timeout / no ChanServ answer also falls back to `#wonderland`.
- `#wonderland` is registered once by Simon (founder); airc is a plain member (no ops).
- Bob ears also JOIN `#wonderland`; Jeeves grants them `+o`. Workers / seats do not join it.
- Ergo reply `Channel #x is registered` counts as registered.
- SASL is on by default for the reserved `{MachineId}_console` nick (NickServ GUID in ConsoleHome).

## Airc vs AircConsole

| | bobiverse **Airc** | agentic_irc **AircConsole** |
|--|--------------------|-----------------------------|
| Root | `<ai root>\airc` | `<ai root>\airc-console` |
| Service | `Airc` | `AircConsole` |
| UpgradeCode | distinct (`…A1BC00A1C001` class) | distinct (`…A1BC00501E01` class) |

Prefer **one** live console per box. `Install-Airc` **removes** leftover `AircConsole` from SCM (on-disk tree may remain).

## Remote shell via PRIVMSG (FR #75 / helper FR #76)

Operators (and the seeded `bob-<machine>` ear nick) may Query the console when AuthPolicy allows them; arbitrary `bob-*` nicks are denied (FR #3286). Default shell is **PowerShell 5.1** (`-NoProfile`); use `cmd:` for COMSPEC; `psb64:` for EncodedCommand. Replies use `out`/`err`/`DONE id= exit=` framing (chunked, not silent 400 clip).

Driving-box helper:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <ai root>\airc\scripts\Invoke-AircRemote.ps1 `
  -MachineId marchhare -Action Status -WhatIf
powershell -NoProfile -ExecutionPolicy Bypass -File <ai root>\airc\scripts\Invoke-AircRemote.ps1 `
  -MachineId marchhare -Action Command -Text "Get-Service Airc" -Outbox $outbox
powershell -NoProfile -ExecutionPolicy Bypass -File <ai root>\airc\scripts\Invoke-AircRemote.ps1 -SelfTest
```

PUT/RUN/JOB verbs are constructed by the helper (sandbox under `<ai root>\airc\drop` by default); server-side acceptance is FR #78.

## Install / secrets / update

- After public MSI: place `<ai root>\airc\config\ergo.password` (or rely on Install copy). **Never invent** the Ergo PASS; NickServ GUID is minted into ConsoleHome `console.password`.
- **FR #3900 (AircConsole → Airc):** Install reads legacy `AircConsole` AppParameters before removing that service, migrates `console.password` into the new home when empty, and on SASL 904 tries one legacy-home password heal. If heal cannot find the old GUID, oper `NickServ SAPASSWD {machine}_console <console.password>` then Restart-Service Airc.
- Re-run `Install-Airc.cmd -MachineId <id>` if NSSM still points at an old tree. On upgrade, omit `-ConsoleHome` so FR #1552 preserve-from-AppParameters runs.
- Service-start self-update is **`Update-BobiverseService.ps1`** (Check mode from `Start-AircConsole.ps1` **-ServiceMode**, or from frozen **`airc.exe`** via `kick_frozen_service_start_hooks` — FR #2401): compares GitHub Releases to `VERSION`, then starts a **detached** Apply helper (scheduled task / WMI). It never runs `msiexec` inline inside the live service process. The frozen host also runs `Sync-BobiverseFromRepo.ps1` when present (same order as Start-AircConsole). Opt out: `BOBIVERSE_NO_UPDATE=1`, `BOB_AUTOUPDATE=0`, or `config\autoupdate.disabled`. Unfrozen Python under Start-AircConsole does **not** re-run the hooks (avoids double Check).
- Optional clone sync when `Sync-BobiverseFromRepo.ps1` is present and `BOBIVERSE_REPO` is set; that path is secondary to the detached release updater.
- Do **not** document or call the retired `Check-BobiverseUpdate.ps1` name for fleet ops.
- **FR #4015 (nssm DisplayName):** never leave unsubstituted `#machine` — resolve `-MachineId` / script id / sanitized `COMPUTERNAME` (fallback `local`) so DisplayName is e.g. `airc console (#walrus IRC shell)`.
- **FR #4014 (no hardcoded #ionos in warnings):** installer/start messages use the target machine id and name `#wonderland` when `#<machine>` is unregistered (e.g. `#walrus is not registered; joining #wonderland`). Never `instead of #ionos`.
- **FR #4013 (non-elevated install / Error 1730):** tip MSI requires `Privileged` (message: `airc install needs administrator rights`) and `InstallPrivileges=elevated` so an unelevated `/i` fails closed before `RemoveExistingProducts` Error **1730** / generic **1603**. `Install-Airc.ps1` self-elevates via UAC; cancel/failure exits **740** with the same plain message and does not write the FR #3759 fail-reported flag / outer intake.
-
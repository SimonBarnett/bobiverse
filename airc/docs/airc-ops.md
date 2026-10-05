# Airc ops (console)

Service **Airc**, tree `<ai root>\airc`, nick **`{MachineId}_console`**.
Canonical **MachineId** is the lowercase sanitized fleet id (`BOB_MACHINE_ID` / `-MachineId`), not a raw Windows `COMPUTERNAME` unless they match.

## ConsoleHome (identity)

| Account | Preferred ConsoleHome |
|---------|------------------------|
| Interactive user | `%USERPROFILE%\.airc` |
| LocalSystem / quiet MSI | `C:\Users\Administrator\.airc` if present, else `<ai root>\airc\home` |
| **Upgrade / reinstall** (FR #1552) | **Existing NSSM `Airc` AppParameters** (`-ConsoleHome`, `-MachineId`, `-PasswordFile`, `-OperatorsFile`, `-File` launcher if still on disk) |

**Never** default to the invoking user's profile when the `Airc` service is already registered — that resets identity and causes SASL 904 / NickServ 433.
**Never** invent a fresh ConsoleHome on MSI upgrade when AppParameters already name one (including a deliberate `Default\.airc` fleet bake).
`Install-Airc.ps1` / `Install-AircConsole.ps1` read `HKLM\...\Services\Airc\Parameters\AppParameters` first; they also write `<ai root>\airc\config\airc-install.json` (paths only, no secrets) and **read that json as fallback** when AppParameters are missing (service already removed).
Fresh installs still migrate legacy `.airc-console` / Default homes when no prior service / json exists.

## Shop vs lobby

- If ChanServ reports `#{MachineId}` registered → JOIN shop as `{MachineId}_console`.
- Else JOIN `#{domain|workgroup}` lobby (`shop-mode=auto` probes `INFO #{machine}`).
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

Authenticated fleet ears (`bob-*`) may Query the console. Default shell is **PowerShell 5.1** (`-NoProfile`); use `cmd:` for COMSPEC; `psb64:` for EncodedCommand. Replies use `out`/`err`/`DONE id= exit=` framing (chunked, not silent 400 clip).

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
- Re-run `Install-Airc.cmd -MachineId <id>` if NSSM still points at an old tree. On upgrade, omit `-ConsoleHome` so FR #1552 preserve-from-AppParameters runs.
- Service-start self-update is **`Update-BobiverseService.ps1`** (Check mode from `Start-AircConsole.ps1` **-ServiceMode**, or from frozen **`airc.exe`** via `kick_frozen_service_start_hooks` — FR #2401): compares GitHub Releases to `VERSION`, then starts a **detached** Apply helper (scheduled task / WMI). It never runs `msiexec` inline inside the live service process. The frozen host also runs `Sync-BobiverseFromRepo.ps1` when present (same order as Start-AircConsole). Opt out: `BOBIVERSE_NO_UPDATE=1`, `BOB_AUTOUPDATE=0`, or `config\autoupdate.disabled`. Unfrozen Python under Start-AircConsole does **not** re-run the hooks (avoids double Check).
- Optional clone sync when `Sync-BobiverseFromRepo.ps1` is present and `BOBIVERSE_REPO` is set; that path is secondary to the detached release updater.
- Do **not** document or call the retired `Check-BobiverseUpdate.ps1` name for fleet ops.
- **ProductCode / uninstall (FR #1552 notes + FR #1566):** ProductCode changes per version — look up uninstall via ARP `DisplayName` `bobiverse airc` (`Get-BobiverseArpProduct` in the updater), never hard-code a GUID. Quiet `msiexec /x` runs deferred `RunUninstall` → `scripts\Uninstall-Airc.cmd` **before RemoveFiles** when `REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE`. That stops/removes the `Airc` service via `Remove-BobiverseService` and **keeps ConsoleHome secrets** (`console.password`, operators, NickServ GUID home). MSI RemoveFiles owns the install tree; uninstall never deletes the profile home. MajorUpgrade skips this CA so FR #1552 can still read live AppParameters. Manual: `Uninstall-Airc.cmd` from the staged scripts dir. If ARP is removed but the service remains on an older MSI, treat that as a bug and file intake.

## Operator smoke (short)

1. `Get-Service Airc` → Running; log shows `chanserv-info status=registered` and join as `{machine}_console`.
2. `Invoke-AircRemote.ps1 -MachineId <id> -Action Status -Outbox <ear-outbox>` (or harmless `Command` `Write-Output ping`) → expect Query `DONE id=… exit=0` once FR #75 is deployed.
3. Sandboxed PUT/RUN (when FR #78 is live): put a tiny file under `<ai root>\airc\drop\…` only.
4. After UPDATE / MSI: wait for `{machine}_console` to answer again within ~120s (detached updater + reconnect); do not inline-msiexec over the live airc transport.

## Verify

```powershell
Get-Service Airc,AircConsole
Get-Content $env:USERPROFILE\.airc\*.log -Tail 40 -ErrorAction SilentlyContinue
# Expect: chanserv-info status=registered; joined #<machine> as <machine>_console
```

## Related

- Helper: `scripts/Invoke-AircRemote.ps1`
- Protocol: `docs/airc-remote-control.md`
- Skills: `.grok/skills/bobiverse-airc*.md`
- Updater: `common/scripts/Update-BobiverseService.ps1` (staged beside product scripts on install)

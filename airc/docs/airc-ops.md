# Airc ops (console)

Service **Airc**, tree `<ai root>\airc`, nick **`{MachineId}_console`**.
Canonical **MachineId** is the lowercase sanitized fleet id (`BOB_MACHINE_ID` / `-MachineId`), not a raw Windows `COMPUTERNAME` unless they match.

## ConsoleHome (identity)

| Account | Preferred ConsoleHome |
|---------|------------------------|
| Interactive user | `%USERPROFILE%\.airc` |
| LocalSystem / quiet MSI | `C:\Users\Administrator\.airc` if present, else `<ai root>\airc\home` |

**Never** `C:\Users\Default\.airc` — that orphans the NickServ GUID (`console.password`).
`Install-Airc.ps1` migrates legacy `.airc-console` / Default homes when needed.

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
- Re-run `Install-Airc.cmd -MachineId <id>` if NSSM still points at an old tree.
- Service-start self-update is **`Update-BobiverseService.ps1`** (Check mode from `Start-AircConsole.ps1` / product start): compares GitHub Releases to `VERSION`, then starts a **detached** Apply helper (scheduled task / WMI). It never runs `msiexec` inline inside the live service process. Opt out: `BOBIVERSE_NO_UPDATE=1`, `BOB_AUTOUPDATE=0`, or `config\autoupdate.disabled`.
- Optional clone sync when `Sync-BobiverseFromRepo.ps1` is present and `BOBIVERSE_REPO` is set; that path is secondary to the detached release updater.
- Do **not** document or call the retired `Check-BobiverseUpdate.ps1` name for fleet ops.

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

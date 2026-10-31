# Airc ops (console)

Service **Airc**, tree `<ai root>\airc`, nick **`{MachineId}_console`**.
Canonical **MachineId** is the lowercase sanitized fleet id (`BOB_MACHINE_ID` / `-MachineId`), not a raw Windows `COMPUTERNAME` unless they match.

## ConsoleHome (identity)

| Account | Preferred ConsoleHome |
|---------|------------------------|
| Interactive user | `%USERPROFILE%\.airc` |
| LocalSystem / quiet MSI | `C:\Users\Administrator\.airc` if present, else `<ai root>\airc\home` |
| **Upgrade / reinstall** (FR #1552) | **Existing NSSM `Airc` AppParameters** (PowerShell `-ConsoleHome` / `-MachineId` / ... or airc.exe `--home` / `--machine` / `--password-file` / `--operators-file`) |

## airc-network-installer.exe (FR #3991)

Elevated network-wide airc MSI installer shipped in every airc release:

- **Build:** `airc/scripts/Build-AircNetworkInstaller.ps1` (PyInstaller one-file with `--uac-admin`).
- **Release assets:** `airc-network-installer-<ver>.exe` + `.sha256` next to the MSI (Pack writes them under `dist/`).
- **Laid in the airc MSI** at `<ai root>\airc\airc-network-installer.exe` so any installed airc box can re-run it.
- **MSI source:** always downloads the GitHub **Latest** `airc-*.msi` + `.sha256` (refuses on hash mismatch). `--msi` is testing-only.
- **Profile:** `--profile fleet|client|workstation` (default `client`) passed as msiexec public property `AIRC_PROFILE=...` (same property WiX / Install-Airc use).
- **Service name:** Windows service `Airc`. Skip if same/newer; upgrade if older; `--force` reinstalls. Local host is always a target (unless `--no-local`); local install uses msiexec directly; remotes use PsExec (`\\host -accepteula -h -s`) without bundling PsExec (Sysinternals licence). With `-u`, password is prompted via getpass and used for `net use` only --- never on PsExec argv.
- **Targets:** AD computers when domain-joined; else `--hosts` / `--hosts-file` / `--network CIDR`. Logs under `./airc-install-logs/<host>/` + `summary.csv`. `--dry-run` plans only. Exit non-zero if any host failed (0 and 3010 count as success).

Smoke: `airc-network-installer.exe --selftest` and `--help`. Pack test stages use `-SkipAircNetworkInstallerExe` with `-SkipMsi`.

## airc.exe (FR #2397)

`Pack-BobiverseRelease -Product airc` runs `airc/scripts/Build-Airc.ps1` (PyInstaller one-file) and stages `airc\airc.exe` in the MSI. `Install-AircConsole` prefers that exe as NSSM `Application` with argparse AppParameters; when the exe is missing it keeps the legacy `powershell.exe` + `Start-AircConsole.ps1` path. Smoke: `airc.exe --selftest` and `airc.exe --help`. Target boxes do not need system Python for the console service once the exe is installed.

## Antivirus exclusions before install (FR #4215)

Consumer AV (Windows Defender, Avast, AVG, ...) can refuse creating unsigned `airc.exe` on disk. Install registers exclusions **before** the exe is laid:

1. **MSI:** deferred `RunAvExclude` CA (Defender `ExclusionPath` / `ExclusionProcess`) scheduled **Before=`InstallFiles`**.
2. **`Install-Airc.ps1` / standalone `Install-AircConsole.ps1`:** `common/scripts/Register-BobiverseAvExclusions.ps1` — Defender path/process (+ Controlled Folder Access allow) and best-effort Avast/AVG FileShield registry lists. Failures are WARN-only; install continues.

If Avast still blocks, add a manual File/Folder exception for `<ai root>\airc` (and `airc.exe`) in the Avast UI.

**Never** default to the invoking user's profile when the `Airc` service is already registered --- that resets identity and causes SASL 904 / NickServ 433.
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
| UpgradeCode | distinct (`...A1BC00A1C001` class) | distinct (`...A1BC00501E01` class) |

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

## Hung shell recovery (FR #5211)

- If partial `out id=...` arrives without `DONE`, try `CANCEL id=<shell-id>` from the same authorized Query nick. It cancels that active or queued shell with `DONE ... exit=130`; other queued commands continue. PUT/RUN cancellation keeps its existing protocol.
- `STATUS` is handled independently of the shell queue. If STATUS also times out, check the ear's `airc-replies.jsonl` and the client's Airc log for disconnect/restart evidence; a missing DONE alone does not prove a running shell is hung.
- If the console remains unresponsive, run `Restart-Service Airc` locally on the **affected client**, or through an independent authorized administration channel. Restart **only Airc**; never Ergo/BobIrcd, seats, or broad process names. Then retry STATUS followed by a short command.
- Shell capture is bounded by the shell timeout (default 120 seconds, plus bounded process cleanup), without waiting for descendant pipe EOF. UTF-16 BOM output is decoded, invalid UTF-8 is replaced, and NUL is replaced before IRC framing. Do not dump configuration files containing credentials; inspect only known non-secret fields.
- A source hotpatch requires the usual backup and Airc-only restart. Frozen `airc.exe` needs a separately approved rebuild/redeploy; changing Python source beside it does not patch the running executable.

## Install / secrets / update

- **FR #4216:** airc MSI embeds `<ai root>\airc\config\ergo.password`; Install seeds ConsoleHome from it. Pack fails closed without `AIRC_PACK_ERGO_PASSWORD` / packer connect.password. **Never invent** the Ergo PASS; NickServ GUID is minted into ConsoleHome `console.password`.
- **FR #3900 (AircConsole -> Airc / 1.0.0 mint):** Install reads legacy `AircConsole` AppParameters before removing that service, prefers prior `PasswordFile` / `airc-install.json` over an empty or install-minted `console.password`, writes `console.password-minted` on mint so the service skips SASL (not FR #3863 reuse), and on SASL 904 tries one legacy-home / install-json password heal. If heal cannot find the old GUID, oper `NickServ PASSWD {machine}_console <console.password>` then Restart-Service Airc. Ergo has `PASSWD` only (not `SAPASSWD`).
- **FR #4388 (walrus / DC SASL 904 after tip upgrade):** #3900 heal alone is not enough when no alternate GUID file exists (LocalSystem already wrote the wrong mint into the live home). Tip expands legacy scan to SystemProfile / ProgramData homes, and when heal still finds nothing does a one-shot `OPER` + `NickServ PASSWD {machine}_console <console.password>` using `oper.cred` / `BOB_OPER_*` / discovered `ergo-oper*` (never logs the secret), then reconnects for SASL. If no oper credentials are available the loud PASSWD ERROR remains.
- **FR #4579 (walrus 1.0.x upgrade profile + mint):** Empty MSI/CLI `AIRC_PROFILE` preserves `profile` from `config\airc.json` / `airc-install.json` (so a failed `AIRC_PROFILE=client` property does not rewrite fleet and re-enable `self_update`). Upgrade refuses to mint a new `console.password` when the live file is still empty after prefer-prior (would desync NickServ for an existing `{machine}_console`).
- Re-run `Install-Airc.cmd -MachineId <id>` if NSSM still points at an old tree. On upgrade, omit `-ConsoleHome` so FR #1552 preserve-from-AppParameters runs.
- Service-start self-update is **`Update-BobiverseService.ps1`** (Check mode from `Start-AircConsole.ps1` **-ServiceMode**, or from frozen **`airc.exe`** via `kick_frozen_service_start_hooks` --- FR #2401): compares GitHub Releases to `VERSION`, then starts a **detached** Apply helper (scheduled task / WMI). It never runs `msiexec` inline inside the live service process. The frozen host also runs `Sync-BobiverseFromRepo.ps1` when present (same order as Start-AircConsole). Opt out: `BOBIVERSE_NO_UPDATE=1`, `BOB_AUTOUPDATE=0`, or `config\autoupdate.disabled`. Unfrozen Python under Start-AircConsole does **not** re-run the hooks (avoids double Check).
- **FR #5079 (side-by-side tip console):** for a from-source / tip nick beside production NSSM `Airc`, use `scripts\Start-AircConsoleSideBySide.ps1 -Nick <other>_console -ConsoleHome <dir>` (passes Python `--log-file`; no `Start-Process -RedirectStandardOutput`). Parent-shell pipe redirects die when the launcher PowerShell exits and kill the host after NAMES sync.
- Optional clone sync when `Sync-BobiverseFromRepo.ps1` is present and `BOBIVERSE_REPO` is set; that path is secondary to the detached release updater.
- Do **not** document or call the retired `Check-BobiverseUpdate.ps1` name for fleet ops.
- **FR #4011 (PsExec SYSTEM upgrade 1601 / Restart Manager 351):** Quiet upgrades under `psexec \\host -h -s msiexec ... /qn` run in session 0. Restart Manager cannot shut down the Airc service (error 351) and Windows Installer itself can crash (exit **1601**, SCM 7031). Tip MSI bakes `MSIRESTARTMANAGERCONTROL=Disable` and stops Airc (`sc stop Airc`) before `InstallValidate` / `RemoveExistingProducts`. For an older MSI still on the wire, pass the property explicitly, e.g. `msiexec /i airc-<ver>.msi AIRC_PROFILE=client MSIRESTARTMANAGERCONTROL=Disable /qn /norestart /l*v C:\Temp\msi-install.log`. **Release checklist:** after packing airc, verify `psexec \\walrus -h -s msiexec /i ... MSIRESTARTMANAGERCONTROL=Disable /qn` upgrades 0.1.30->tip exits 0 and keep the verbose log.
- **FR #4432 (upgrade 1603 / Error 2613 + empty QuietExec cmdline):** Do **not** schedule a deferred CA before `RemoveExistingProducts` after `InstallInitialize` (Windows Installer Error **2613** → msiexec **1603**). airc MajorUpgrade uses `Schedule=afterInstallValidate` so REP runs before `InstallInitialize`. The upgrade stop is an **immediate** `CAQuietExec64` that sets `QtExec64CmdLine` (immediate QuietExec does not read a property named after the CA — that pattern is deferred CustomActionData only). Symptom of the old 1.0.1 pack: `StopAircBeforeUpgrade` deferred at 1502 then REP at 1503 → 2613; `StopAircBeforeValidate` immediate with Property=CA id → `Failed to get command line data` / FilesInUse.
- **FR #4441 (bake hotfix1 net stop):** Pack uses `net.exe stop Airc` on `QtExec64CmdLine` (not `sc.exe`). `net stop` waits for the service to stop so files unlock before InstallValidate/REP; matches proven `airc-1.0.1-hotfix1.msi` on walrus (msiexec exit 0, no Error 2613). Keep MajorUpgrade `afterInstallValidate` from FR #4432.
- **FR #4389 (three-part ProductVersion + FilesInUse 3010):** MSI `Product/@Version` compares only **major.minor.build** (3 fields). A four-part marketing tag such as `1.0.0.1` is equal to `1.0.0` for MajorUpgrade, so `msiexec /i` installs **side-by-side** (two ARP entries) and never sets `WIX_UPGRADE_DETECTED` — the service stays up, FilesInUse fires, and quiet installs exit **3010**. Pack folds `x.y.z.w` → `x.y.(z+w)` via `ConvertTo-BobiverseMsiProductVersion` (so `1.0.0.1` → `1.0.1`) for ProductVersion / stage VERSION / BUILD.json.version while the MSI filename still uses the release tag. On upgrade the MSI stops Airc before `InstallValidate`. Prefer three-part release tags for new airc/bob/jeeves packs.
- **FR #4012 (Error 1705 pending transaction):** a crashed msiexec (e.g. companion 1601) can leave `HKLM\...\Installer\InProgress` so the next `/i` hits Error **1705**. `Clear-BobiverseMsiPendingTransaction` (Bobiverse-Common) removes InProgress/Rollback when no live msiexec is running and restarts `msiserver`; `Invoke-BobiverseMsiexecSerialized` calls it before msiexec and retries exit 1705. `Install-Airc.cmd` also clears before Install-Airc.ps1. Manual psexec: run the clear helper (or re-run via Update-BobiverseService) before a second `/i`.
- **ProductCode / uninstall (FR #1552 notes + FR #1566 / FR #3292 / FR #3392):** ProductCode changes per version --- look up uninstall via ARP `DisplayName` `bobiverse airc` (`Get-BobiverseArpProduct` in the updater), never hard-code a GUID. Quiet `msiexec /x` runs deferred `RunUninstall` -> `scripts\Uninstall-Airc.cmd` **before RemoveFiles** when `REMOVE="ALL" AND NOT UPGRADINGPRODUCTCODE`. That stops/removes the `Airc` service via `Remove-BobiverseService`. **Fleet default keeps ConsoleHome secrets** (`console.password`, operators, NickServ GUID home). **Workstation** installs (`AIRC_PROFILE=workstation`) strip MSI-laid agent briefings/skills/scripts at install (FR #3392) and on uninstall / `AIRC_PURGE=1` purge ConsoleHome, config/logs/.git/.grok, `Users\Default\.airc*`, `ProgramData\Bobiverse\update\airc`, `ProgramData\Bobiverse\logs\install-airc.log`, and LocalSystem crash-spool (manifest `%ProgramData%\Bobiverse\airc-install-manifest.json`). FR #3394: install locks `%ProgramData%\Bobiverse` and the install tree fail-closed before `Start-Service`; purge refuses manifest paths outside the allow-list. MSI RemoveFiles owns the remaining heat-laid tree. MajorUpgrade skips this CA so FR #1552 can still read live AppParameters. Manual: `Uninstall-Airc.cmd -Purge 1` for a full wipe. If ARP is removed but the service remains on an older MSI, treat that as a bug and file intake.

## Operator smoke (short)

1. `Get-Service Airc` -> Running; log shows `chanserv-info status=registered` and join as `{machine}_console`.
2. `Invoke-AircRemote.ps1 -MachineId <id> -Action Status -Outbox <ear-outbox>` (or harmless `Command` `Write-Output ping`) -> expect Query `DONE id=... exit=0` once FR #75 is deployed.
3. Sandboxed PUT/RUN (when FR #78 is live): put a tiny file under `<ai root>\airc\drop\...` only.
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
- **FR #4015 (nssm DisplayName):** never leave unsubstituted `#machine` --- resolve `-MachineId` / script id / sanitized `COMPUTERNAME` (fallback `local`) so DisplayName is e.g. `airc console (#walrus IRC shell)`.
- **FR #4030 (fleet / Bob remote shell ON):** fleet installs default `shell=operators` (1.0.0: fresh-default was `off` when Bob detect missed). Upgrade migrates legacy fresh-default / unmarked `shell=off` unless `shell_source=explicit`. Console `WARN` logs shell=off on Bob with source. Workstation profile still defaults off.
- **FR #5295 (EXTENSION cap):** fleet `extension=on`; client and workstation default `extension=off`. Cap-off reply is `DONE exit=126 extension-disabled`. Unauthorized stays `DONE exit=126 not-op`. `update=off` still refuses EXTENSION. MSI `AIRC_EXTENSION=on|off`.
- **FR #4390:** ON is the value `operators` (AppParameters `--shell-mode operators`). The JSON key is named `shell`; never write or expect `"shell": "shell"`.
- **FR #4014 (no hardcoded #ionos in warnings):** installer/start messages use the target machine id and name `#wonderland` when `#<machine>` is unregistered (e.g. `#walrus is not registered; joining #wonderland`). Never `instead of #ionos`.
- **FR #4013 (non-elevated install / Error 1730):** tip MSI requires `Privileged` (message: `airc install needs administrator rights`) and `InstallPrivileges=elevated` so an unelevated `/i` fails closed before `RemoveExistingProducts` Error **1730** / generic **1603**. `Install-Airc.ps1` self-elevates via UAC; cancel/failure exits **740** with the same plain message and does not write the FR #3759 fail-reported flag / outer intake.
- **FR #5312 / #5594 (LEGION):** `LEGION {host|ip}` [-WhatIf] is UPDATE-class. Isolated worker imports `airc_network_installer` (FR #3991). Default identity is LocalSystem / the source computer account (must be a local Administrator on the target). CredMan `PriorityAirc/LegionAdmin` is off-by-default (`AIRC_LEGION_USE_CREDMAN=1`). DCCLISTEN same job id or CONT. Never secrets on IRC.

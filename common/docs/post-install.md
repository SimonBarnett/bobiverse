# Post-install notes (bobiverse MSI)

## After `msiexec /i *-*.msi`
0. **Where is `<ai root>`?** It is the `<drive>:\ai` found on the fixed disks (env `BOB_AI_ROOT` / `msiexec ... AIROOT=D:\ai` override), `<SystemDrive>:\ai` only when no fixed disk has one. See README "The `<drive>:\ai` root". Never assume `C:\ai`.

1. **ObjectName password (ircBob / ircJeeves)**  
   Services must run as the fleet **user** (DPAPI), not LocalSystem.  
   - Interactive `Install-*.ps1 -PromptServicePassword` prompts for the Windows password.  
   - Silent / MSI `/qn`: set machine env `BOBIVERSE_SERVICE_PASSWORD` before install, **or** drop `<ai root>\<product>\config\service.password` (one line), **or** run Desktop **Complete bobiverse service logon**.  
   - Quiet MSI never calls `Get-Credential` (issue #6).  
   - Password is saved as DPAPI `config\service.cred` for reinstalls.

2. **Ergo server PASS**  
   Public release MSIs **do not** embed `config\ergo.password` (issue #4).  
   After install, place one line at `<ai root>\<product>\config\ergo.password` or `~\.grok\ergo\connect.password`, or set `BOB_IRC_PASSWORD`.  
   Private/offline packs may use `Pack-BobiverseRelease.ps1 -EmbedErgoPassword`.

3. **NickServ / SASL (Bob ear)**  
   Reserved `Bob-*` / `bob-*` nicks need SASL (issue #8 / #11).  
   `Start-Bob.ps1` loads `home\nickserv.password` into `BOB_IRC_SASL_USER=bob-{machine}` + `BOB_IRC_SASL_PASSWORD`.  
   When those env vars are set, `irc_agent` authenticates **before** NICK so Ergo accepts the reserved nick.  
   Do **not** mint a fresh GUID for an account that already exists on the network â€” restore the real password or oper-`SAREGISTER` / `RESETPASS`.  
   If stdout shows `INFO no-sasl reason=â€¦`, `INFO NICKNAME_RESERVED`, or abort `NICKNAME_RESERVED`, fix NickServ credentials â€” not `!register` (that is ChanServ shops).  
   Fleet `Bob-*` ears no longer silently fall back to `Bob-â€¦_l`.

4. **LocalSystem fallback**  
   If ObjectName stays LocalSystem, NSSM **omits** `-BobHome` so `Start-Bob` uses `<ai root>\bob\home` (issue #7). Prefer completing service logon.

5. **Self-copy**  
   MSI already stages `<ai root>\<product>`. Install scripts skip copying onto themselves (issue #2).

6. **Ear CLI**  
   `Start-Bob.ps1` uses `--channel "#bobiverse,#<machine>"` (issue #3).

7. **Python deps**  
   Install runs `pip install cryptography` into the selected Python.

8. **Airc shop channel**  
   With `shop-mode=auto`, Airc probes ChanServ `INFO #{machine}`. Ergo replies `Channel #x is registered` â€” that counts as registered (join `#{machine}` as `{machine}_console`).

8b. **Airc ConsoleHome under quiet MSI / LocalSystem**  
   Quiet MSI runs install as LocalSystem. Do **not** use `C:\Users\Default\.airc` â€” that orphans the NickServ GUID from the Admin home and leaves `{machine}_console` reserved with a password the service no longer has (`sasl-fail 904` / `433` loop).  
   `Install-Airc` prefers `C:\Users\Administrator\.airc` when present, else `<ai root>\airc\home`.  
   `Start-AircConsole` / `airc_console_service.py` default **SASL on** so reserved `{machine}_console` authenticates before NICK.

8c. **Reclaim `{machine}_console` after a wrong GUID (oper)**  
   If the service log shows `sasl-fail 904` then `nick-in-use 433` for `{machine}_console`:
   1. Read the GUID on the box: `Get-Content C:\Users\Administrator\.airc\console.password` (or `<ai root>\airc\home\console.password`).
   2. As an Ergo oper with `accreg`: `/OPER â€¦` then `/msg NickServ PASSWD {machine}_console <guid>`.
   3. `Restart-Service Airc` and confirm `joined #{machine} as {machine}_console` without a `433` loop.  
   `ERASE` also works (`/msg NickServ ERASE {machine}_console` then confirm with the code) but requires the same oper cap; without `/OPER`, NickServ replies `Command restricted` (easy to miss in Halloy Notices).

9. **Bootstrap tools (issue #10)**  
   Quiet MSI runs install as LocalSystem. `Install-BootstrapTools.ps1` resolves well-known per-user paths for `gh` / Python before winget. Missing `gh` soft-fails (update-check limited); missing git/python/node still fails the install.

10. **Airc vs airc-console UpgradeCode (issue #12)**  
    bobiverse `airc` MSI uses UpgradeCode `B7E3C9A1-4F2D-4E8B-9C11-A1BC00A1C001`, distinct from agentic_irc `airc-console`. They can coexist (`<ai root>\airc` / service `Airc` vs `<ai root>\airc-console` / `AircConsole`). Prefer one console per box.

## Verify Bob

```powershell
Get-Service ircBob
Get-Content <ai root>\bob\logs\stdout.log -Tail 40
# or:
Get-Content <ai root>\bob\home\irc.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content $env:USERPROFILE\.bobiverse\irc.log -Tail 40 -ErrorAction SilentlyContinue
```

Expect:

- `INFO SASL user=bob-<machine> from â€¦\nickserv.password` (when file present)
- `INFO connecting irc.ntsa.uk:6697`
- `INFO joined #bobiverse,#<machine> as Bob-<machine>`

If you see `INFO no-sasl` then `INFO NICKNAME_RESERVED` / `NO 001`, fix NickServ SASL credentials before retrying.

## Verify Airc

Remote control protocol (current + FR): [airc-remote-control.md](./airc-remote-control.md).

```powershell
Get-Service Airc,AircConsole
# NSSM AppStdout path, or:
Get-Content $env:USERPROFILE\.airc\*.log -Tail 40 -ErrorAction SilentlyContinue
```

Expect `chanserv-info status=registered` and `joined #<machine> as <machine>_console` when the shop is ChanServ-registered.

`Install-Airc` **removes** leftover agentic_irc `AircConsole` from the SCM so only bobiverse `Airc` remains (on-disk `<ai root>\airc-console` tree may remain).

## Verify Jeeves (Ergo host)

```powershell
Get-Service ircJeeves,BobJeeves,BobIrcd
Get-Content <ai root>\jeeves\logs\stdout.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content <ai root>\jeeves\logs\stderr.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content $env:USERPROFILE\.jeeves\irc.log -Tail 40 -ErrorAction SilentlyContinue
```

Expect:

- Legacy **`BobJeeves` absent** from SCM (Install-Jeeves removes it â€” both chairs fight for nick `Jeeves`; `<ai root>\ergo` tree may remain)
- `ircJeeves` Running; ObjectName = fleet user when `service.password` / `BOBIVERSE_SERVICE_PASSWORD` was supplied
- Log: `joined #bobiverse,#â€¦ as Jeeves`

### LocalSystem / DPAPI pitfalls

Quiet MSI runs as LocalSystem. If ObjectName stays LocalSystem:

- Do **not** use `C:\Users\Default\.jeeves` (Install-Jeeves avoids Default; prefers Admin chair or `<ai root>\jeeves\home-jeeves`).
- Admin-sealed `identity.json` cannot be opened â†’ `CryptUnprotectData failed` crash-loop.
  - Fix properly: `Complete-BobiverseServiceLogon.ps1 -Product jeeves` with `<ai root>\jeeves\config\service.password`.
  - Interim: rename `identity.json` â†’ `identity.json.admin-dpapi.bak` so LocalSystem mints a fresh identity (SEAL key changes).

Never pass unquoted `#channel` in PowerShell AppParameters / one-liners â€” `#` starts a comment. `Start-Jeeves` omits `--channel`; `irc_agent --chair` defaults the seed channel.

### Remote ops via airc

From a fleet bob ear outbox (UTF-8 no BOM):

```text
PRIVMSG {machine}_console :sc query ircJeeves
```

Keep commands short; stage longer fixes with `irm` + `powershell -File`.

## Tray (ircBob companion TipForm)

From **0.1.7** the bob MSI ships the full TipForm systray (`tools\Watch-BobTray.ps1` + BobBridge under `<ai root>\bob`), launched by `scripts\Start-BobTray.ps1` â†’ `tools\Start-BobFleetTray.ps1` as an **interactive companion** to the `ircBob` Windows service (Desktop / Start Menu / per-user Startup + HKCU `Run\BobiverseTray`). It is **not** a `BobFleet-*` scheduled task â€” disable any leftover `BobFleet-<MachineId>` task after upgrade.

- **Durable start (0.1.8+):** `Start-BobFleetTray` starts the seat wrapper with **WMI `Win32_Process.Create`** so TipForm survives agent/console job-object teardown. Do not rely on `Start-Process -PassThru` from a Grok Build shell.
- **Digest webhook:** TipForm calls `Write-BobIrcStatus` about every 30s and POSTs usage to `reportUrl` (`https://irc.ntsa.uk/bob/v1/report` from `config\bobiverse.json`). No password/secret is used: the digest accepts the POST because this machine id is on the roster Jeeves publishes (ChanServ mirror).
- **Restart** on the TipForm menu (label **Restart**, not "Restart ircBob") calls `Restart-BobTrayWatcher` → `Start-BobFleetTray -ForceNew`, which restarts `ircBob` via `Restart-BobTrayService` / `Invoke-BobTrayServiceControl.ps1` and relaunches TipForm in the interactive session. Do not confuse this with raw `nssm restart ircBob`.
- **Ear-only recycle:** Desktop / Start Menu **Restart ircBob** / `scripts\Restart-BobEar.ps1` announces departure then `Restart-Service ircBob` (no tray relaunch by itself).
- Product updates on **service** start only: `scripts\Sync-BobiverseFromRepo.ps1` fast-forwards the bobiverse clone (`<ai root>\bobiverse` or `BOBIVERSE_REPO`) and syncs into `<ai root>\<product>`; MSI `Check-BobiverseUpdate.ps1` is the fallback when no clone exists. Skip with `BOBIVERSE_NO_UPDATE=1`.
- TipForm systray is a **watcher**: ordinary tray Start does **not** Sync/ff; TipForm **Restart** recycles the ear (so Start-Bob Sync/ff runs) and brings the tray back. Quiet MSI registers logon task `BobiverseTray` (`Start-BobTrayInteractive.ps1`) so TipForm is not started in session 0.
- Vendored pin: `<ai root>\bob\PIN.txt` (agentic_build SHA used at pack time). TipForm footer shows `bob {VERSION}`.

Smoke (optional): `scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot <ai root>\bob`.

## Start Menu (single folder)

Every installer (Bob, Jeeves, Airc) maintains ONE all-users folder, `Start Menu\Programs\Bobiverse`
(`C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Bobiverse`), and removes older top-level duplicates
(`Bob Systray*`, `Bobiverse Tray*`, `Bob Fleet*`, `Restart ircBob`, `Bob Services`, `Complete bobiverse service logon*`,
a `Bob Systray` folder, per-user `Bobiverse` folders) on every install/upgrade. Every shortcut uses `assets\bob-systray.ico`.
Per product: Bob Services; Bobiverse Tray (bob); Restart ircBob / ircJeeves / Airc; Complete bobiverse service logon (<product>,
only while the service has no ObjectName); Logs (<product>); Skill books (<product>); Agent guide (<product>);
Jeeves command reference (jeeves). Inventory test: `tests/test_start_menu_020.py`.

## Agent-start layer

Each installed service dir (`<ai root>\bob`, `<ai root>\jeeves`, `<ai root>\airc`) gets `AGENTS.md`, `CLAUDE.md`, `GROK.md`,
`.cursor\rules\bobiverse-<product>.mdc` and `.grok\skills\bobiverse-<product>*` + `bobiverse-fleet-ops` + `harvest*`.
All start with the CAST IRON RULE: harvest skills and file every issue/FR/bug to the intake webhook
(`scripts\Report-BobiverseIntakeIssue.ps1`, `scripts\Invoke-BobiverseHarvest.ps1`). The installers deploy them
(`Install-BobiverseAgentLayer`) and the self-updater / `Sync-BobiverseFromRepo.ps1` refresh them. Tests: `tests/test_agent_layer_020.py`.

## MSI RunInstall properties (#70)

Public msiexec properties are forwarded into the deferred `RunInstall` custom action (no MSI transform required):

- **jeeves**: `OPERFILE=`, `OPERNAME=`, `OPACCOUNTS=`, `SKIPERGO=1`, `SKIPCOPY=1`
- **bob**: `MACHINEID=`, `IRCHOST=`, `SKIPCOPY=1`
- **airc**: `MACHINEID=`

Example: `msiexec /i jeeves-0.1.19.msi /qn OPERFILE=C:\secure\oper.txt SKIPERGO=1`

Empty properties expand to empty strings and are ignored by `Install-*.ps1`.

## Upgrade and Ergo / BobIrcd (#70)

Jeeves MSI packs mark `third_party\nssm\win64\nssm.exe` and `ergo\ergo.exe` as **Permanent + NeverOverwrite** so an upgrade does not rewrite the service binary or a hard-linked Ergo image. `Install-Jeeves` also runs `Repair-BobiverseErgoHardlink` when `<ai root>\ergo\ergo.exe` still shares a hard link with the pack copy (no service stop).

Complete service logon after quiet MSI: Desktop / Start Menu **Complete bobiverse service logon**, or set `BOBIVERSE_SERVICE_PASSWORD` / `config\service.password` before install (see ObjectName above).
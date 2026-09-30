# Post-install notes (bobiverse MSI)

## After `msiexec /i *-*.msi`

1. **ObjectName password (ircBob / ircJeeves)**  
   Services must run as the fleet **user** (DPAPI), not LocalSystem.  
   - Interactive `Install-*.ps1 -PromptServicePassword` prompts for the Windows password.  
   - Silent / MSI `/qn`: set machine env `BOBIVERSE_SERVICE_PASSWORD` before install, **or** drop `C:\ai\<product>\config\service.password` (one line), **or** run Desktop **Complete bobiverse service logon**.  
   - Quiet MSI never calls `Get-Credential` (issue #6).  
   - Password is saved as DPAPI `config\service.cred` for reinstalls.

2. **Ergo server PASS**  
   Public release MSIs **do not** embed `config\ergo.password` (issue #4).  
   After install, place one line at `C:\ai\<product>\config\ergo.password` or `~\.grok\ergo\connect.password`, or set `AGENTIC_IRC_PASSWORD`.  
   Private/offline packs may use `Pack-BobiverseRelease.ps1 -EmbedErgoPassword`.

3. **NickServ / SASL (Bob ear)**  
   Reserved `Bob-*` / `bob-*` nicks need SASL (issue #8 / #11).  
   `Start-Bob.ps1` loads `home\nickserv.password` into `AGENTIC_IRC_SASL_USER=bob-{machine}` + `AGENTIC_IRC_SASL_PASSWORD`.  
   When those env vars are set, `irc_agent` authenticates **before** NICK so Ergo accepts the reserved nick.  
   Do **not** mint a fresh GUID for an account that already exists on the network — restore the real password or oper-`SAREGISTER` / `RESETPASS`.  
   If stdout shows `INFO no-sasl reason=…`, `INFO NICKNAME_RESERVED`, or abort `NICKNAME_RESERVED`, fix NickServ credentials — not `!register` (that is ChanServ shops).  
   Fleet `Bob-*` ears no longer silently fall back to `Bob-…_l`.

4. **LocalSystem fallback**  
   If ObjectName stays LocalSystem, NSSM **omits** `-BobHome` so `Start-Bob` uses `C:\ai\bob\home` (issue #7). Prefer completing service logon.

5. **Self-copy**  
   MSI already stages `C:\ai\<product>`. Install scripts skip copying onto themselves (issue #2).

6. **Ear CLI**  
   `Start-Bob.ps1` uses `--channel "#bobiverse,#<machine>"` (issue #3).

7. **Python deps**  
   Install runs `pip install cryptography` into the selected Python.

8. **Airc shop channel**  
   With `shop-mode=auto`, Airc probes ChanServ `INFO #{machine}`. Ergo replies `Channel #x is registered` — that counts as registered (join `#{machine}` as `{machine}_console`).

8b. **Airc ConsoleHome under quiet MSI / LocalSystem**  
   Quiet MSI runs install as LocalSystem. Do **not** use `C:\Users\Default\.airc` — that orphans the NickServ GUID from the Admin home and leaves `{machine}_console` reserved with a password the service no longer has (`sasl-fail 904` / `433` loop).  
   `Install-Airc` prefers `C:\Users\Administrator\.airc` when present, else `C:\ai\airc\home`.  
   `Start-AircConsole` / `airc_console_service.py` default **SASL on** so reserved `{machine}_console` authenticates before NICK.

8c. **Reclaim `{machine}_console` after a wrong GUID (oper)**  
   If the service log shows `sasl-fail 904` then `nick-in-use 433` for `{machine}_console`:
   1. Read the GUID on the box: `Get-Content C:\Users\Administrator\.airc\console.password` (or `C:\ai\airc\home\console.password`).
   2. As an Ergo oper with `accreg`: `/OPER …` then `/msg NickServ PASSWD {machine}_console <guid>`.
   3. `Restart-Service Airc` and confirm `joined #{machine} as {machine}_console` without a `433` loop.  
   `ERASE` also works (`/msg NickServ ERASE {machine}_console` then confirm with the code) but requires the same oper cap; without `/OPER`, NickServ replies `Command restricted` (easy to miss in Halloy Notices).

9. **Bootstrap tools (issue #10)**  
   Quiet MSI runs install as LocalSystem. `Install-BootstrapTools.ps1` resolves well-known per-user paths for `gh` / Python before winget. Missing `gh` soft-fails (update-check limited); missing git/python/node still fails the install.

10. **Airc vs airc-console UpgradeCode (issue #12)**  
    bobiverse `airc` MSI uses UpgradeCode `B7E3C9A1-4F2D-4E8B-9C11-A1BC00A1C001`, distinct from agentic_irc `airc-console`. They can coexist (`C:\ai\airc` / service `Airc` vs `C:\ai\airc-console` / `AircConsole`). Prefer one console per box.

## Verify Bob

```powershell
Get-Service ircBob
Get-Content C:\ai\bob\logs\stdout.log -Tail 40
# or:
Get-Content C:\ai\bob\home\irc.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content $env:USERPROFILE\.agentic-irc-bobiverse\irc.log -Tail 40 -ErrorAction SilentlyContinue
```

Expect:

- `INFO SASL user=bob-<machine> from …\nickserv.password` (when file present)
- `INFO connecting irc.ntsa.uk:6697`
- `INFO joined #bobiverse,#<machine> as Bob-<machine>`

If you see `INFO no-sasl` then `INFO NICKNAME_RESERVED` / `NO 001`, fix NickServ SASL credentials before retrying.

## Verify Airc

```powershell
Get-Service Airc,AircConsole
# NSSM AppStdout path, or:
Get-Content $env:USERPROFILE\.airc\*.log -Tail 40 -ErrorAction SilentlyContinue
```

Expect `chanserv-info status=registered` and `joined #<machine> as <machine>_console` when the shop is ChanServ-registered.

`Install-Airc` **removes** leftover agentic_irc `AircConsole` from the SCM so only bobiverse `Airc` remains (on-disk `C:\ai\airc-console` tree may remain).

## Verify Jeeves (Ergo host)

```powershell
Get-Service ircJeeves,BobJeeves,BobIrcd
Get-Content C:\ai\jeeves\logs\stdout.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content C:\ai\jeeves\logs\stderr.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content $env:USERPROFILE\.agentic-irc-jeeves\irc.log -Tail 40 -ErrorAction SilentlyContinue
```

Expect:

- Legacy **`BobJeeves` absent** from SCM (Install-Jeeves removes it — both chairs fight for nick `Jeeves`; `C:\ai\ergo` tree may remain)
- `ircJeeves` Running; ObjectName = fleet user when `service.password` / `BOBIVERSE_SERVICE_PASSWORD` was supplied
- Log: `joined #bobiverse,#… as Jeeves`

### LocalSystem / DPAPI pitfalls

Quiet MSI runs as LocalSystem. If ObjectName stays LocalSystem:

- Do **not** use `C:\Users\Default\.agentic-irc-jeeves` (Install-Jeeves avoids Default; prefers Admin chair or `C:\ai\jeeves\home-jeeves`).
- Admin-sealed `identity.json` cannot be opened → `CryptUnprotectData failed` crash-loop.
  - Fix properly: `Complete-BobiverseServiceLogon.ps1 -Product jeeves` with `C:\ai\jeeves\config\service.password`.
  - Interim: rename `identity.json` → `identity.json.admin-dpapi.bak` so LocalSystem mints a fresh identity (SEAL key changes).

Never pass unquoted `#channel` in PowerShell AppParameters / one-liners — `#` starts a comment. `Start-Jeeves` omits `--channel`; `irc_agent --chair` defaults the seed channel.

### Remote ops via airc

From a fleet bob ear outbox (UTF-8 no BOM):

```text
PRIVMSG {machine}_console :sc query ircJeeves
```

Keep commands short; stage longer fixes with `irm` + `powershell -File`.

## Tray (ircBob companion TipForm)

From **0.1.7** the bob MSI ships the full TipForm systray (`tools\Watch-BobTray.ps1` + BobBridge under `C:\ai\bob`), launched by `scripts\Start-BobTray.ps1` → `tools\Start-BobFleetTray.ps1` as an **interactive companion** to the `ircBob` Windows service (Desktop / Start Menu / per-user Startup + HKCU `Run\BobiverseTray`). It is **not** a `BobFleet-*` scheduled task — disable any leftover `BobFleet-<MachineId>` task after upgrade.

- **Durable start (0.1.8+):** `Start-BobFleetTray` starts the seat wrapper with **WMI `Win32_Process.Create`** so TipForm survives agent/console job-object teardown. Do not rely on `Start-Process -PassThru` from a Grok Build shell.
- **Digest webhook:** TipForm calls `Write-BobIrcStatus` about every 30s and POSTs usage to `reportUrl` (`https://irc.ntsa.uk/bob/v1/report` from `config\bobiverse.json`). Auth header `X-Bob-Secret` comes from `BOB_REPORT_SECRET` or `~\.grok\bob\report.secret` (never in git / MSI).
- **Restart** on the TipForm menu recycles the **tray watcher** (and IRC logout announce), not `nssm restart ircBob`. Use Desktop **Bob Fleet Restart** / `scripts\Restart-BobEar.ps1` to recycle the ear service.
- Product updates on **service** start only: `scripts\Sync-BobiverseFromRepo.ps1` fast-forwards the bobiverse clone (`C:\ai\bobiverse` or `BOBIVERSE_REPO`) and syncs into `C:\ai\<product>`; MSI `Check-BobiverseUpdate.ps1` is the fallback when no clone exists. Skip with `BOBIVERSE_NO_UPDATE=1`.
- TipForm systray is a **watcher**: ordinary tray Start does **not** Sync/ff. TipForm **Restart ircBob** calls `Restart-BobEar` (service recycle → Start-Bob Sync/ff) then relaunches the tray in the interactive session. Quiet MSI registers logon task `BobiverseTray` (`Start-BobTrayInteractive.ps1`) so TipForm is not started in session 0.
- Vendored pin: `C:\ai\bob\PIN.txt` (agentic_build SHA used at pack time). TipForm footer shows `bob {VERSION}`.

Smoke (optional): `scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot C:\ai\bob`.

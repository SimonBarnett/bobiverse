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
   Reserved `Bob-*` / `bob-*` nicks need SASL (issue #8).  
   `Start-Bob.ps1` loads `home\nickserv.password` into `AGENTIC_IRC_SASL_USER=bob-{machine}` + `AGENTIC_IRC_SASL_PASSWORD`.  
   Mint or oper-`SAREGISTER` that account before expecting `001`.  
   If stdout shows `INFO NICKNAME_RESERVED` / `INFO FAIL … NICKNAME_RESERVED`, fix NickServ (ERASE/SAREGISTER/IDENTIFY) — not `!register` (that is ChanServ shops).

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
Get-Service Airc
# NSSM AppStdout path, or:
Get-Content $env:USERPROFILE\.airc\*.log -Tail 40 -ErrorAction SilentlyContinue
```

Expect `chanserv-info status=registered` and `joined #<machine> as <machine>_console` when the shop is ChanServ-registered.

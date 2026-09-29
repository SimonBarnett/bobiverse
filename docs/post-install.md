# Post-install notes (bobiverse MSI)

## After `msiexec /i *-*.msi`

1. **ObjectName password (ircBob / ircJeeves)**  
   Services must run as the fleet **user** (DPAPI), not LocalSystem.  
   - Interactive install prompts for the Windows password.  
   - Silent / MSI without password: set machine env `BOBIVERSE_SERVICE_PASSWORD` before install, **or** drop `C:\ai\<product>\config\service.password` (one line), **or** run Desktop **Complete bobiverse service logon**.  
   - Password is saved as DPAPI `config\service.cred` for reinstalls.

2. **Ergo server PASS**  
   Embedded in the MSI as `config\ergo.password` (intentional). `Start-Bob` / `Start-Jeeves` load it into `AGENTIC_IRC_PASSWORD`. Operator `~\.grok\ergo\connect.password` is also accepted.

3. **Self-copy**  
   MSI already stages `C:\ai\<product>`. Install scripts skip copying onto themselves (issue #2).

4. **Ear CLI**  
   `Start-Bob.ps1` uses `--channel "#bobiverse,#<machine>"` (issue #3).

5. **Python deps**  
   Install runs `pip install cryptography` into the selected Python.

6. **LocalSystem fallback**  
   If ObjectName is still LocalSystem, home is `C:\ai\bob\home` and `protect_path` soft-fails icacls 1332. Prefer completing service logon.

## Verify Bob

```powershell
Get-Service ircBob
Get-Content $env:USERPROFILE\.agentic-irc-bobiverse\irc.log -Tail 40
# or under LocalSystem fallback:
Get-Content C:\ai\bob\home\irc.log -Tail 40
```

Expect `INFO connecting irc.ntsa.uk:6697` and `JOIN #bobiverse`.

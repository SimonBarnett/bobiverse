# Airc ops (console)

Service **Airc**, tree `C:\ai\airc`, nick **`{MachineId}_console`**.
Console home: `%USERPROFILE%\.airc` (often Administrator when NSSM is LocalSystem).

## Shop vs lobby

- If ChanServ reports `#{MachineId}` registered → JOIN shop as `{MachineId}_console`.
- Else JOIN `#{domain|workgroup}` lobby (`shop-mode=auto` probes `INFO #{machine}`).
- Ergo reply `Channel #x is registered` counts as registered.

## Airc vs AircConsole

| | bobiverse **Airc** | agentic_irc **AircConsole** |
|--|--------------------|-----------------------------|
| Root | `C:\ai\airc` | `C:\ai\airc-console` |
| Service | `Airc` | `AircConsole` |
| UpgradeCode | `…A1BC00A1C001` | `…A1BC00501E01` |

Prefer **one** live console per box. Install-Airc **removes** leftover `AircConsole` from SCM (on-disk tree may remain).

## Remote shell via PRIVMSG

Authenticated fleet ears (`bob-*`) may:

```text
PRIVMSG win-mpre8vi4u6u_console :sc query ircJeeves
```

- Shell is **cmd.exe** under the service account (often SYSTEM).
- Keep commands short (IRC line length). Stage scripts with `irm` then `powershell -File`.
- Avoid killing broad `powershell.exe` — can take down Airc’s host process.
- After a kill: `Restart-Service Airc` until `{machine}_console` is visible again.

## Install / secrets

- After public MSI: place `C:\ai\airc\config\ergo.password` (or `~\.grok\ergo\connect.password`).
- Re-run `Install-Airc.cmd -MachineId <id>` if NSSM still points at an old airc-console tree.
- Self-update on start: `Sync-BobiverseFromRepo.ps1` (`git fetch` + `merge --ff-only origin/main` on `C:\ai\bobiverse` / `BOBIVERSE_REPO`, then robocopy `scripts`/`third_party`/`VERSION` into `C:\ai\airc`). Falls back to `Check-BobiverseUpdate.ps1` when no clone exists. Skip with `BOBIVERSE_NO_UPDATE=1`.

## Verify

```powershell
Get-Service Airc,AircConsole
Get-Content $env:USERPROFILE\.airc\*.log -Tail 40 -ErrorAction SilentlyContinue
# Expect: chanserv-info status=registered; joined #<machine> as <machine>_console
```

## Related

- Skill: `.grok/skills/bobiverse-airc/SKILL.md`
- Post-install: `docs/post-install.md`

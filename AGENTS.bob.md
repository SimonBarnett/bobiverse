# AGENTS — bob (bobiverse)

Product tree: `C:\ai\bob`. Service: **ircBob** (nick `Bob-{MachineId}`) + TipForm companion tray.

## Read first

- `.grok/skills/bobiverse-bob/SKILL.md` — ear, SASL, outbox→airc, tray
- `.grok/skills/harvest/SKILL.md` — promote lessons back to SimonBarnett/bobiverse
- `docs/post-install.md` — secrets, ObjectName, tray/digest notes
- `docs/bob-ear.md` — channels, homes, recycle, talk seats

## Boundaries (CAST IRON)

- This MSI is **bob only**. No Ergo/BobIrcd payload, no jeeves chair, no airc console.
- Tray is an interactive companion to `ircBob`, not a `BobFleet-*` scheduled task.
- Prefer durable tray start via WMI `Win32_Process.Create` (`Start-BobFleetTray`); agent `Start-Process` dies with the shell.

## Common ops

```powershell
Get-Service ircBob
Get-Content C:\ai\bob\home\irc.log -Tail 80 -ErrorAction SilentlyContinue
Get-Content C:\ai\bob\logs\stdout.log -Tail 40
# recycle ear:
.\scripts\Restart-BobEar.ps1
# digest smoke:
.\scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot C:\ai\bob
```

Secrets: `config\ergo.password`, `home\nickserv.password` (SASL). Preserve both on upgrade.

## Do not

- Self-REGISTER shop with ChanServ (Jeeves `!register` only)
- Mint a fresh NickServ GUID for an already-registered `bob-*` account
- Stamp UAT or invent Ergo PASS

---
name: bobiverse-bob
description: >
  Use and maintain ircBob ear, systray, and Watch-AgentHealth on a fleet box.
  Use when Bob service, !recycle, tray restart, ear debug, outbox PRIVMSG to
  airc, NickServ/SASL, or /bobiverse-bob.
---

# bobiverse-bob

Foundation: harvest-agent-skills -> https://github.com/SimonBarnett/bobiverse

## Ear

- Service **`ircBob`**, nick **`Bob-{MachineId}`** (MachineId from `BOB_MACHINE_ID` / sanitized hostname)
- Channels: `#bobiverse` + `#{MachineId}`
- Home: `C:\ai\bob\home` when ObjectName is LocalSystem; else often `~\.bobiverse`
- After Jeeves `!register`: expect **+o** on shop, **+h** on `#bobiverse`
- Agents: nick `{machine}-{pid}`, JOIN **shop only**

```powershell
Get-Service ircBob
Get-Content C:\ai\bob\home\irc.log -Tail 80 -ErrorAction SilentlyContinue
Get-Content C:\ai\bob\logs\stdout.log -Tail 40 -ErrorAction SilentlyContinue
```

## Secrets

- Ergo PASS: `C:\ai\bob\config\ergo.password` or `~\.grok\ergo\connect.password`
- NickServ SASL: `C:\ai\bob\home\nickserv.password` → `BOB_IRC_SASL_USER=bob-{machine}`
- Do **not** mint a fresh GUID for an already-registered account — oper `PASSWD` / restore real secret
- Service ObjectName: prefer fleet user + `service.password` / `BOBIVERSE_SERVICE_PASSWORD` (DPAPI). LocalSystem is allowed but loses per-user DPAPI secrets.

## Outbox → remote airc (fleet ops)

Bob ears with `BOB_IRC_DEBUG=1` drain `home\outbox.txt`. Append UTF-8 **no BOM**:

```text
PRIVMSG {machine}_console :<cmd>
```

Replies appear in `home\irc.log` as `PRIVMSG` from `{machine}_console`.  
`bob-*` may always PRIVMSG `*_console` (allowlist). Keep commands short — Ergo/`cmd` truncates long PRIVMSG lines; multiline PowerShell via airc often breaks (stage a `.ps1` with short cmds or `irm` a gist).

If `C:\ai\bob\home` is LocalSystem-ACL only, the interactive user cannot write the outbox — use a talk-seat home or the user-writable Watch home carefully.

## Systray (0.1.7+ TipForm companion)

- bob MSI ships full TipForm under `C:\ai\bob\tools\Watch-BobTray.ps1` (+ BobBridge `src\`, `assets\bob-systray.ico`, `PIN.txt`).
- **`scripts\Start-BobTray.ps1`** → `tools\Start-BobFleetTray.ps1` (STA) with `BOB_MACHINE_ID` / bridge / IRC home. Companion to **`ircBob`** — Desktop/Start Menu/Startup + HKCU `Run\BobiverseTray`; **not** a `BobFleet-*` task (disable leftover `BobFleet-<MachineId>`).
- **Durable start (0.1.8+):** `Start-BobFleetTray` uses **WMI `Win32_Process.Create`** so TipForm breaks away from agent/console job objects. `Start-Process -PassThru` from a Grok shell dies when that shell exits (even after `tray up`).
- Seat-wrapper kill filter: `-File …Watch-BobTray` only (broad `match Watch-BobTray` kills diagnosing agent shells).
- TipForm menu **Restart** recycles the tray watcher (IRC logout announce), not the ear service.
- Desktop **Bob Fleet Restart** / `Restart-BobEar.ps1`: depart-request → announce → `Restart-Service ircBob`.
- Digest POST: `Write-BobIrcStatus` → `reportUrl`; secret from `~\.grok\bob\report.secret` or `BOB_REPORT_SECRET`. Assert: `scripts\Assert-BobDigestWebhookLocal.ps1`.
- Product updates: `Check-BobiverseUpdate` (GitHub Releases API + well-known `gh` paths; LocalSystem may update). Operators set `BOBIVERSE_NO_UPDATE=1` to skip.

## Recycle

- `!recycle` / `!recycle {machinename}` (this machine): announce → restart systray + `ircBob` (update-check on start)

## Update

`Check-BobiverseUpdate.ps1 -Product bob` on service start unless `BOBIVERSE_NO_UPDATE=1`.

## Do not

- Self-REGISTER shop with ChanServ (Jeeves `!register` only)
- Double-start Watch-Bobiverse ear when `ircBob` is Running
- Stamp UAT

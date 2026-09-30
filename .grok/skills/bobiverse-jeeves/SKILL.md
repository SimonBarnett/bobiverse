---
name: bobiverse-jeeves
description: >
  Maintain and debug ircJeeves + BobIrcd on the Ergo host. Use when Jeeves
  service, !register, !recycle jeeves, ChanServ, cutover from BobJeeves,
  CryptUnprotectData, ChairHome Default profile, or /bobiverse-jeeves.
---

# bobiverse-jeeves

Foundation: harvest-agent-skills -> https://github.com/SimonBarnett/bobiverse

## Services

- `ircJeeves` — nick **Jeeves**, `irc_agent.py --chair` (bobiverse)
- `BobIrcd` — Ergo TLS :6697
- Legacy **`BobJeeves`** (gh-Jeeves `python -m jeeves`) — **disable** on cutover; both fight for nick Jeeves

```powershell
Get-Service ircJeeves,BobJeeves,BobIrcd
Get-Content C:\ai\jeeves\logs\stderr.log -Tail 80 -ErrorAction SilentlyContinue
Get-Content $env:USERPROFILE\.agentic-irc-jeeves\irc.log -Tail 80
```

## Homes and DPAPI (CAST IRON)

- Chair home: `~\.agentic-irc-jeeves` (or Admin path on Ergo host).
- Digest: `BOB_DIGEST_HOME=~\.agentic-irc-bobiverse`.
- **ObjectName must be the install user** (DPAPI) — not LocalSystem.
  - Quiet MSI: `BOBIVERSE_SERVICE_PASSWORD` or `C:\ai\jeeves\config\service.password` (one line) before install, or Desktop **Complete bobiverse service logon**.
  - LocalSystem + Admin-sealed `identity.json` → `OSError: CryptUnprotectData failed` and crash-loop.
  - Interim: park `identity.json` → `identity.json.admin-dpapi.bak`, let LocalSystem mint a fresh identity (SEAL key changes). Prefer fixing ObjectName and restoring the bak when the password is available.
- MSI as LocalSystem must **not** bake `C:\Users\Default\.agentic-irc-jeeves` into NSSM AppParameters. Install-Jeeves prefers existing `C:\Users\Administrator\.agentic-irc-jeeves`, else `C:\ai\jeeves\home-jeeves`.

## Start-Jeeves / --channel

- `Start-Jeeves.ps1` launches `--chair --nick Jeeves --home …` (no `--channel`).
- `irc_agent.py`: `--channel` is optional when `--chair`; defaults to `bobiverse`. Chair channel list comes from `bobreport.chair_channels()`.
- Never pass unquoted `#bobiverse` in a PowerShell command line — `#` starts a comment and drops the rest of the argv (symptom: `error: the following arguments are required: --channel` or `expected one argument`).

## Ergo

Ergo payload: MSI `ergo\` → live root **`C:\ai\ergo`** (`Install-BobIrcd.ps1`).
First boot may seed `ircd.yaml` from `default.yaml` — set TLS, server PASS, ChanServ/NickServ registration.
`config\ergo.password` (or `~\.grok\ergo\connect.password`) required after public MSI.

## Cutover checklist (Ergo host)

1. `Stop-Service BobJeeves; Set-Service BobJeeves -StartupType Disabled` (Install-Jeeves does this).
2. Ensure `C:\ai\jeeves\config\ergo.password` exists (copy from `~\.grok\ergo\connect.password`).
3. Set ObjectName via `Complete-BobiverseServiceLogon.ps1 -Product jeeves` when `service.password` is available.
4. `Restart-Service ircJeeves`
5. Expect stdout/irc.log: `joined #bobiverse,#… as Jeeves` and GIT announces on `#bobiverse`.

NSSM AppStdout/AppStderr should be `C:\ai\jeeves\logs\*.log` so crash loops do not flood the airc console pipe.

## Commands

- `!register <machine>` — Simon/operators; ChanServ REGISTER `#{machine}`
- `!recycle jeeves` — departure announce; restart `ircJeeves` only (not BobIrcd)
- Existing chair: `!recycle <machine>`, `!list`, digest/GIT/`chair-outbox`

## Restart / update

Service start runs `Check-BobiverseUpdate.ps1 -Product jeeves` unless `BOBIVERSE_NO_UPDATE=1`.
Ergo recycle: `Restart-Service BobIrcd` (separate from jeeves).

## Do not

- Invent Ergo PASS
- Run legacy BobJeeves and ircJeeves together
- Stamp UAT

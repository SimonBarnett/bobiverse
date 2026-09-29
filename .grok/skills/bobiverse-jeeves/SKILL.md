---
name: bobiverse-jeeves
description: >
  Maintain and debug ircJeeves + BobIrcd on the Ergo host. Use when Jeeves
  service, !register, !recycle jeeves, ChanServ, or /bobiverse-jeeves.
---

# bobiverse-jeeves

Foundation: harvest-agent-skills -> https://github.com/SimonBarnett/bobiverse

## Services

- `ircJeeves` — nick **Jeeves**, `--chair`
- `BobIrcd` — Ergo TLS :6697

```powershell
Get-Service ircJeeves,BobIrcd
Get-Content $env:USERPROFILE\.agentic-irc-jeeves\irc.log -Tail 80
```

Homes: `~\.agentic-irc-jeeves`, `BOB_DIGEST_HOME=~\.agentic-irc-bobiverse`.
ObjectName must be the install **user** (DPAPI) — not LocalSystem.
Use `Install-Jeeves.ps1 -PromptServicePassword` or env `BOBIVERSE_SERVICE_PASSWORD`.

Ergo payload: MSI `ergo\` → live root **`C:\ai\ergo`** (`Install-BobIrcd.ps1`).
First boot may seed `ircd.yaml` from `default.yaml` — set TLS, server PASS, ChanServ/NickServ registration.

## Commands

- `!register <machine>` — Simon/operators; ChanServ REGISTER `#{machine}`
- `!recycle jeeves` — departure announce; restart `ircJeeves` only (not BobIrcd)
- Existing chair: `!recycle <machine>`, `!list`, digest/GIT/`chair-outbox`

## Restart / update

Service start runs `Check-BobiverseUpdate.ps1 -Product jeeves` unless `BOBIVERSE_NO_UPDATE=1`.
Ergo recycle: `Restart-Service BobIrcd` (separate from jeeves).

## Do not

- Invent Ergo PASS
- Stamp UAT

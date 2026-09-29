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

## Commands

- `!register <machine>` — Simon/operators; ChanServ REGISTER `#{machine}`
- `!recycle jeeves` — departure announce; restart `ircJeeves` (MSI self-update on start)
- Existing chair: `!recycle <machine>`, `!list`, digest/GIT/`chair-outbox`

## Restart / update

Service start runs `Check-BobiverseUpdate.ps1 -Product jeeves` unless `BOBIVERSE_NO_UPDATE=1`.

## Do not

- Invent Ergo PASS
- Stamp UAT

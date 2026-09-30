# AGENTS — jeeves (bobiverse)

Product tree: `C:\ai\jeeves`. Services: **ircJeeves** (chair nick `Jeeves`), **BobIrcd** (Ergo).

## Read first

- `.grok/skills/bobiverse-jeeves/SKILL.md` — install, DPAPI, cutover, recycle
- `.grok/skills/harvest/SKILL.md` — promote lessons back to SimonBarnett/bobiverse
- `docs/post-install.md` — ObjectName password, Ergo PASS, verify checklist
- `docs/jeeves-admin.md` — Ergo host admin, ChanServ, !register
- `docs/webhooks.md` — `/bob/v1/report|git|intake|jira` curls

## Boundaries (CAST IRON)

- This MSI is **jeeves only**. Do not expect bob seat, TipForm, Watch-AgentHealth, or airc console here.
- Legacy **BobJeeves** must be removed from SCM; it fights for nick `Jeeves`.
- ObjectName must be the fleet user (DPAPI). LocalSystem + Admin-sealed `identity.json` crash-loops.

## Common ops

```powershell
Get-Service ircJeeves,BobJeeves,BobIrcd
Get-Content C:\ai\jeeves\logs\stderr.log -Tail 80
Complete-BobiverseServiceLogon.ps1 -Product jeeves   # when service.password present
Restart-Service ircJeeves
```

Chair home: `~\.agentic-irc-jeeves` (or Admin / `C:\ai\jeeves\home-jeeves`). Digest: `BOB_DIGEST_HOME=~\.agentic-irc-bobiverse`.

## Do not

- Invent Ergo PASS or stamp UAT
- Ship or edit bob/airc product skills in this tree
- Bump VERSION / pack MSI unless the operator asked

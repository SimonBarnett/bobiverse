# AGENTS - jeeves (bobiverse)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

Product tree: `<ai root>\jeeves`. Services: **ircJeeves** (chair nick `Jeeves`), **BobIrcd** (Ergo, separate), task **BobCallback** (webhooks :7700). This file is also shipped as `CLAUDE.md`, `GROK.md` and
`.cursor/rules/bobiverse-jeeves.mdc` so any agent (Grok, Claude, Cursor, ...) started in this directory has the same briefing.

## What you are looking at

Jeeves is the deterministic, token-less fleet chair: channel privileges (+o/+h), ChanServ roster, job queue (webhooks + 15-min authenticated GitHub resync), the gh-Jeeves command set (`!help !list !filter !status !resync !sweep !ignore !focus !recycle ping`), the digest and the public webhooks (`/bob/v1/report|digest|git|intake|jira` behind IIS). A 30-min probe watches the webhooks and announces only on up<->down.

## Read first (in this order)

- `.grok/skills/bobiverse-jeeves/SKILL.md` - architecture, paths, ports, config, logs, background jobs, install/DPAPI/cutover
- `.grok/skills/bobiverse-jeeves-commands/SKILL.md` - every command, authorization, how to test as the bob ear
- `.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md` - failure playbook
- `.grok/skills/bobiverse-fleet-ops/SKILL.md` - shared health checks, hotpatch, rollback, privilege rules, tests
- `.grok/skills/harvest/SKILL.md` - harvest + intake

Docs in `docs\`:
- `jeeves-commands.md` (command reference + authorization matrix), `jeeves-admin.md` (Ergo host admin, ChanServ, !register), `webhooks.md` (curls), `post-install.md`, `channel-privileges-and-workers.md`

## Hard rules (CAST IRON)

- **Hotpatch safely**: back up the install tree first; copy only the changed files; restart ONLY this product's service;
  never touch Ergo (`<ai root>\ergo`, `ircd.yaml`) or `BobIrcd`; never kill or disturb seats/agents/tray; never print or
  commit secrets (`*.password`, `github.token`, `identity.json`, oper cred, NickServ GUIDs); PowerShell only on Windows
  (never wrap in `powershell -Command`). Full procedure: `bobiverse-fleet-ops`.
- **Machine ids** are lowercase sanitized hostnames (`<machine>`): shop `#<machine>`, ear `Bob-<machine>`, console `<machine>_console`.
- **Do not** rebuild, release, bump `VERSION` or merge unless the owner says so; do not stamp UAT; do not invent an Ergo PASS.
- **Always finish with the harvest step** (rule above) - file every issue/FR/bug and every learned playbook.

## Common ops

```powershell
Get-Service ircJeeves,BobIrcd
Get-Content <ai root>\jeeves\logs\stdout.log -Tail 80
Get-Content $env:USERPROFILE\.jeeves\cmd-trace.log -Tail 40      # timed command replies (chair home may be Administrator's)
Complete-BobiverseServiceLogon.ps1 -Product jeeves                 # when service.password is present
Restart-Service ircJeeves                                          # ONLY this service
.\scripts\Invoke-BobiverseHarvest.ps1 -Summary '...' -Lesson '...'   # end of every session
```

## Do not

- Invent Ergo PASS or stamp UAT; ship or edit bob/airc product skills in this tree
- Run legacy `BobJeeves` with `ircJeeves`; bump VERSION / pack an MSI unless the operator asked


## Install dir = git work tree (t781u/t782u)

`<ai root>\jeeves` is a sparse git work tree of the bobiverse repo holding only `jeeves/` + `common/`. Every service start fetches and fast-forwards it (ff-only, only while it is on `main`, never touching your edits/commits/branches, never blocking the start) and recomposes the flat runtime files from it. You can: file intake issues (`scripts\Report-BobiverseIntakeIssue.ps1`), work on the repo right here (`git switch -c fix/x`, edit `jeeves\...` / `common\...`, commit, `git push -u origin fix/x`, PR) and new commits on `main` arrive on the next service restart. Edit the tracked folders, not the flat copies. Opt out: `BOBIVERSE_NO_UPDATE=1`. Details: README "The install dir is a git work tree".
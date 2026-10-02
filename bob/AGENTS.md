# AGENTS - bob (bobiverse)

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

Product tree: `<ai root>\bob`. Services: **ircBob** (ear nick `Bob-<machine>`) + the TipForm tray companion. This file is also shipped as `CLAUDE.md`, `GROK.md` and
`.cursor/rules/bobiverse-bob.mdc` so any agent (Grok, Claude, Cursor, ...) started in this directory has the same briefing.

## What you are looking at

The Bob ear is this box's presence on IRC (`#bobiverse` + `#<machine>`): shop channel, digest reports, local `!recycle`, outbox PRIVMSGs, talk seats. It is also an authorized principal for Jeeves ops commands. The tray is an interactive companion, not a service.

## Read first (in this order)

- `.grok/skills/bobiverse-bob/SKILL.md` - architecture, paths, config, tray, install/hotpatch
- `.grok/skills/bobiverse-bob-commands/SKILL.md` - what the ear handles; typing as the ear via outbox.txt
- `.grok/skills/bobiverse-bob-troubleshooting/SKILL.md` - restart loops (--host), SASL, outbox BOM, tray
- `.grok/skills/bobiverse-bob-worker/SKILL.md` - the tray **Agent** item / `bob-worker.exe`: how a worker seat starts (cursor > grok > key prompt), ONE window, `!bored`, IRC relay, IRC-loss exit, hang restarts, logs
- `.grok/skills/bobiverse-bob-job-irc/SKILL.md` (+ `-fr`, `-mrb`, `-uat`) - exact ACK / DONE / NACK / GIVEUP lines and the FR / MRB / UAT job processes (with diagrams) a worker follows
- `.grok/skills/bobiverse-bob-plan/SKILL.md` - the tray **Plan** item: `bob-worker.exe --mode plan` in `<ai root>\bob\plan` (visionary / plan skills)
- `.grok/skills/bobiverse-fleet-ops/SKILL.md` - shared health checks, hotpatch, rollback, privilege rules, tests
- `.grok/skills/harvest/SKILL.md` - harvest + intake

Docs in `docs\`:
- `bob-ear.md` (channels, homes, recycle, talk seats), `post-install.md` (secrets, ObjectName, tray/digest), `jeeves-commands.md` is on the Jeeves box

## Agent and Plan (tray, single click each)

- The tray has two plain items, **Agent** and **Plan** (no submenus). Each click runs `bob-worker.exe` (`<ai root>\bob\worker`) which starts a **NEW** agent
  every time - it NEVER resumes, continues or attaches to an existing agent session, window or process (no `--resume`/`--continue`).
- The agent is chosen automatically by token availability: Cursor pool > 0 -> `agent.cmd`; else local Grok weekly tokens -> `agent.exe`; else a hidden-input prompt in the same window asks for a Grok session key.
- Agent CWD is `<ai root>\bob\worker`; Plan CWD is `<ai root>\bob\plan`. Both folders have their own AGENTS.md + skills with the CAST IRON harvest rule on top.
- Full start / troubleshooting guide: `bobiverse-bob-worker` and `bobiverse-bob-plan`.

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
Get-Service ircBob
Get-Content <ai root>\bob\logs\stdout.log -Tail 40
.\scripts\Restart-BobEar.ps1                 # announce departure, restart ircBob only
.\scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot <ai root>\bob
.\scripts\Invoke-BobiverseHarvest.ps1 -Summary '...' -Lesson '...'   # end of every session
```

## Do not

- Self-REGISTER the shop with ChanServ (Jeeves `!register` only); mint a fresh NickServ GUID for a registered `bob-*` account
- Start the tray with `Start-Process` from an agent shell (use `Start-BobTray.ps1`); stamp UAT or invent an Ergo PASS


## Install dir = git work tree (t781u/t782u)

`<ai root>\bob` is a sparse git work tree of the bobiverse repo holding only `bob/` + `common/`. Every service start fetches and fast-forwards it (ff-only, only while it is on `main`, never touching your edits/commits/branches, never blocking the start) and recomposes the flat runtime files from it. You can: file intake issues (`scripts\Report-BobiverseIntakeIssue.ps1`), work on the repo right here (`git switch -c fix/x`, edit `bob\...` / `common\...`, commit, `git push -u origin fix/x`, PR) and new commits on `main` arrive on the next service restart. Edit the tracked folders, not the flat copies. Opt out: `BOBIVERSE_NO_UPDATE=1`. Details: README "The install dir is a git work tree".
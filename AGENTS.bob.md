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

Product tree: `C:\ai\bob`. Services: **ircBob** (ear nick `Bob-<machine>`) + the TipForm tray companion. This file is also shipped as `CLAUDE.md`, `GROK.md` and
`.cursor/rules/bobiverse-bob.mdc` so any agent (Grok, Claude, Cursor, ...) started in this directory has the same briefing.

## What you are looking at

The Bob ear is this box's presence on IRC (`#bobiverse` + `#<machine>`): shop channel, digest reports, local `!recycle`, outbox PRIVMSGs, talk seats. It is also an authorized principal for Jeeves ops commands. The tray is an interactive companion, not a service.

## Read first (in this order)

- `.grok/skills/bobiverse-bob/SKILL.md` - architecture, paths, config, tray, install/hotpatch
- `.grok/skills/bobiverse-bob-commands/SKILL.md` - what the ear handles; typing as the ear via outbox.txt
- `.grok/skills/bobiverse-bob-troubleshooting/SKILL.md` - restart loops (--host), SASL, outbox BOM, tray
- `.grok/skills/bobiverse-fleet-ops/SKILL.md` - shared health checks, hotpatch, rollback, privilege rules, tests
- `.grok/skills/harvest/SKILL.md` - harvest + intake

Docs in `docs\`:
- `bob-ear.md` (channels, homes, recycle, talk seats), `post-install.md` (secrets, ObjectName, tray/digest), `jeeves-commands.md` is on the Jeeves box

## Hard rules (CAST IRON)

- **Hotpatch safely**: back up the install tree first; copy only the changed files; restart ONLY this product's service;
  never touch Ergo (`C:\ai\ergo`, `ircd.yaml`) or `BobIrcd`; never kill or disturb seats/agents/tray; never print or
  commit secrets (`*.password`, `github.token`, `identity.json`, oper cred, NickServ GUIDs); PowerShell only on Windows
  (never wrap in `powershell -Command`). Full procedure: `bobiverse-fleet-ops`.
- **Machine ids** are lowercase sanitized hostnames (`<machine>`): shop `#<machine>`, ear `Bob-<machine>`, console `<machine>_console`.
- **Do not** rebuild, release, bump `VERSION` or merge unless the owner says so; do not stamp UAT; do not invent an Ergo PASS.
- **Always finish with the harvest step** (rule above) - file every issue/FR/bug and every learned playbook.

## Common ops

```powershell
Get-Service ircBob
Get-Content C:\ai\bob\logs\stdout.log -Tail 40
.\scripts\Restart-BobEar.ps1                 # announce departure, restart ircBob only
.\scripts\Assert-BobDigestWebhookLocal.ps1 -InstallRoot C:\ai\bob
.\scripts\Invoke-BobiverseHarvest.ps1 -Summary '...' -Lesson '...'   # end of every session
```

## Do not

- Self-REGISTER the shop with ChanServ (Jeeves `!register` only); mint a fresh NickServ GUID for a registered `bob-*` account
- Start the tray with `Start-Process` from an agent shell (use `Start-BobTray.ps1`); stamp UAT or invent an Ergo PASS
---
name: bobiverse-bob-plan
description: >
  How to start a bob PLAN agent: tray Plan click, bob-worker.exe --mode plan, CWD C:\ai\bob\plan, always-new agent rule, automatic cursor->grok->dialog selection, plan skills, logs, troubleshooting.
---

# bobiverse bob - plan agent

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

How to start a **Plan** agent from the bob install. A Plan is a NEW agent whose working folder is `C:\ai\bob\plan` and whose first instruction is to read the skills in that folder
(`visionary`, `plan-*`, `harvest*`). It has no IRC and no builds.

## Start it

1. **Tray: click `Plan`** - single menu item, NO sub-menu. One click = one NEW plan agent.
2. **Command line**: `& C:\ai\bob\worker\bob-worker.exe --mode plan --install-root C:\ai\bob` (the same exe as the worker; the tray runs its per-user run copy).
3. Preview: `--mode plan --dry-run` prints the automatic selection and the cwd, starts nothing.

## Rules

* **ALWAYS a NEW agent** (t765u): new session id, new console window, no `--resume`/`--continue`/`-r`/`-c`, never an existing window or process. A second click is a second, independent plan.
  The folder `C:\ai\bob\plan` is shared, so the agent is told to put each plan's output in its OWN new subfolder `C:\ai\bob\plan\work\plan-<yyyyMMdd-HHmmss>` and never to touch earlier ones.
* **Agent selection is the same automatic token rule as the worker**: Cursor (high or low pool > 0) -> Grok (local weekly > 0) -> dialog for a session `XAI_API_KEY`
  (memory only, never saved/printed). See `bobiverse-bob-worker`.
* Cursor runs with `--plan --model auto --workspace C:\ai\bob\plan`; Grok with `--permission-mode plan --session-id <new-uuid> --cwd C:\ai\bob\plan`.
* The exe exits as soon as the plan agent is up (fire-and-forget); there is no supervisor, no health restart and no IRC for plans. Closing the plan window ends the plan.

## The plan folder

`C:\ai\bob\plan\AGENTS.md`, `CLAUDE.md`, `GROK.md`, `.cursor\rules`, `.grok\skills\` (visionary, plan-create-repo, plan-git-from-plan, plan-enable-prs, plan-bob-webhooks, harvest-skills-visionary,
harvest, harvest-agent-skills), `docs\templates\vision.md`, `tools\` (vision-pack validator, git webhook helpers). The MSI installs it; the self-updater refreshes it; your plan outputs under `work\` are never touched by an upgrade.

## Logs and troubleshooting

* `%LOCALAPPDATA%\Bobiverse\worker\logs\bob-worker-plan.log` (selection, `plan: started NEW <kind> agent pid=... session=...`); tray `Open log`.
* Exit codes: `0` started, `4` no agent possible / key dialog cancelled, `6` agent died immediately, `64` plan folder missing (bob MSI older than this feature).
* Nothing happens on click: `Open log`; run `--mode plan --dry-run`; check `tools\Get-BobAgentFuel.ps1` output.

File every problem you find: CAST IRON rule at the top.

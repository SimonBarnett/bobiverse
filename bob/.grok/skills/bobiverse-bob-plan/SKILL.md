---
name: bobiverse-bob-plan
description: >
  How to start a bob PLAN agent: tray Plan click, bob-worker.exe --mode plan, CWD <ai root>\bob\plan, always-new agent rule, automatic cursor->grok->key-prompt selection, plan skills, logs, troubleshooting.
---

# bobiverse bob - plan agent

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary -Kind harvest -Title "short title" -Body "what / where / evidence / fix"`
>    (FR #3318: Plan process → skills-visionary; product decisions → `-Repo SimonBarnett/<product>`; never bobiverse harvest for those).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    (use `-Repo SimonBarnett/<product>` for product decisions) then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush`.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

How to start a **Plan** agent from the bob install. A Plan is a NEW agent whose working folder is `<ai root>\bob\plan` and whose first instruction is to read the skills in that folder
(`visionary`, `plan-*`, `harvest*`). It has no IRC and no builds.

## Start it

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

1. **Tray: click `Plan`** - single menu item, NO sub-menu. One click = one NEW plan agent.
2. **Command line**: `& <ai root>\bob\worker\bob-worker.exe --mode plan --install-root <ai root>\bob` (the same exe as the worker; the tray runs its per-user run copy).
3. Preview: `--mode plan --dry-run` prints the automatic selection and the cwd, starts nothing.

## Rules

* **ALWAYS a NEW agent** (t765u): never resume, continue or attach to an older plan agent; new session id, its own single window, no `--resume`/`--continue`/`-r`/`-c`, never an existing window or process. A second click is a second, independent plan.
  The folder `<ai root>\bob\plan` is shared, so the agent is told to put each plan's output in its OWN new subfolder `<ai root>\bob\plan\work\plan-<yyyyMMdd-HHmmss>` and never to touch earlier ones.
* **Agent selection is the same automatic token rule as the worker**: Cursor (high or low pool > 0) -> Grok (local weekly > 0) -> a hidden-input prompt IN THE SAME WINDOW for a session `XAI_API_KEY`
  (memory only, never saved/printed). See `bobiverse-bob-worker`.
* Cursor (`agent.cmd`) runs with `--plan --model auto --workspace <ai root>\bob\plan`; Grok (`agent.exe`) with `--no-auto-update --no-alt-screen --cwd <ai root>\bob\plan --permission-mode plan --session-id <new-uuid>` (FR #2699: same no-auto-update prefix as agent/monitor/maintenance so Plan cannot self-update mid-session).
* **ONE window** (t771u): the exe's console window hosts the plan agent (the agent inherits it - no second console, no watcher window). The exe stays alive exactly as long as the agent: closing the window or killing the
  exe ends the agent (a kill-on-close job object covers a hard kill), and the agent ending ends the exe. There is no IRC, no `!bored`, no health restart for plans.

## The plan folder

`<ai root>\bob\plan\AGENTS.md`, `CLAUDE.md`, `GROK.md`, `.cursor\rules`, `.grok\skills\` (visionary, plan-create-repo, plan-git-from-plan, plan-enable-prs, plan-bob-webhooks, harvest-skills-visionary,
harvest, harvest-agent-skills), `docs\templates\vision.md`, `tools\` (vision-pack validator, git webhook helpers). The MSI installs it; the self-updater refreshes it; your plan outputs under `work\` are never touched by an upgrade.

## Logs and troubleshooting

* `%LOCALAPPDATA%\Bobiverse\worker\logs\bob-worker-plan.log` (selection, `plan: started NEW <kind> agent pid=... session=...`); tray `Open log`.
* Exit codes: `0` the plan agent ended, `4` no agent possible / key prompt cancelled, `6` launch failed, `64` plan folder missing (bob MSI older than this feature).
* Nothing happens on click: `Open log`; run `--mode plan --dry-run`; check `tools\Get-BobAgentFuel.ps1` output.

File every problem you find: CAST IRON rule at the top.

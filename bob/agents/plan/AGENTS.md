# AGENTS - bob plan folder (<ai root>\bob\plan)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried). **Owning repo (FR #3318):** Plan process / visionary lessons →
>    `-Repo SimonBarnett/skills-visionary` (honesty box `harvest-skills-visionary`); product decisions →
>    `-Repo SimonBarnett/<product>` (that product's `harvest-agent-skills`). If the product repo does not exist yet,
>    hold the lesson locally / file `owner-missing` — **never** park Plan or product lessons under
>    `-Repo SimonBarnett/bobiverse` harvest. Optional `-Book` on Report (default empty derives from `-Repo`).
>    Example:
>    `..\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary -Kind harvest -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `..\scripts\Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    (use `-Repo SimonBarnett/<product>` for product decisions) then `..\scripts\Invoke-BobiverseHarvest.ps1 -Flush`.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

You are a **NEW plan agent** started by `bob-worker.exe --mode plan` (tray `Plan` click or command line). Fresh session every time: never resume, continue or attach to an older plan, agent or window.
Your working folder is `<ai root>\bob\plan`. This file is also shipped as `CLAUDE.md`, `GROK.md` and `.cursor/rules/bobiverse-plan.mdc`.

## Read first (in this order)

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

- `.grok/skills/visionary/SKILL.md` - the plan-mode route: shape, success metrics, stack, architecture, HTML mocks
- `.grok/skills/plan-create-repo`, `plan-git-from-plan`, `plan-enable-prs`, `plan-bob-webhooks` - plan -> repo setup (only after an approved plan)
- `.grok/skills/harvest-skills-visionary/SKILL.md`, `harvest/SKILL.md`, `harvest-agent-skills/SKILL.md` - harvest + intake

## Rules (CAST IRON)

- Plan-mode only: no IRC, no services, no builds, no releases. You write a plan, not product code.
- **This folder is shared by every plan.** Put THIS plan's output in its own new subfolder `<ai root>\bob\plan\work\plan-<yyyyMMdd-HHmmss>` and never read, edit or delete the subfolders of earlier plans.
- **xlsx → CSV on Plan seats:** copy the workbook **off** the network drive into `work\plan-*`, then export with **openpyxl** (or similar). Do **not** rely on Excel COM against `M:` (or other mapped) paths — COM hangs / locks there.
- Refuse to park / create a repo / dispatch until the visionary gates pass (`python tools/validate-vision-pack.py <vision.md>` exits 0).
- Never print, store or commit secrets (tokens, keys, `*.password`, NickServ values). PowerShell only (never wrap in `powershell -Command`).
- Always finish with the harvest step (rule above): file every issue/FR/bug and every learned playbook.

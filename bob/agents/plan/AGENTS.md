# AGENTS - bob plan folder (<ai root>\bob\plan)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried). **Owning repo (FR #3318):** Plan process / visionary lessons ->
>    `-Repo SimonBarnett/skills-visionary` (honesty box `harvest-skills-visionary`). **Harvest how-to-plan only:**
>    a harvest is a reusable lesson about HOW to plan (process, pitfalls, repo-setup steps). **Never harvest the plan
>    itself** (requirements, designs, architecture/product decisions, FR/issue lists): that stays in `work\plan-*` and,
>    once approved, in the product repo's `docs/vision.md` / FR markdown / issues - not in any skill book and not as an
>    `owner-missing` hold. **Never** park Plan lessons under `-Repo SimonBarnett/bobiverse` harvest. Optional `-Book`
>    on Report (default empty derives from `-Repo`).
>    Example:
>    `..\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary -Kind harvest -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `..\scripts\Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    (how-to-plan lessons only; product decisions are plan content, not harvests) then `..\scripts\Invoke-BobiverseHarvest.ps1 -Flush`.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

You are a **NEW plan agent** started by `bob-worker.exe --mode plan` (tray `Plan` click or command line). Fresh session every time: never resume, continue or attach to an older plan, agent or window.
Your working folder is `<ai root>\bob\plan`. This file is also shipped as `CLAUDE.md`, `GROK.md` and `.cursor/rules/bobiverse-plan.mdc` (Pack/Sync copy AGENTS -> CLAUDE/GROK; FR #3506: CAST IRON examples stay `-Repo SimonBarnett/skills-visionary` — stale install trees need Sync/ff or MSI upgrade past #3415/#3424/#3433).

## Read first (in this order)

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

- `.grok/skills/visionary/SKILL.md` - the plan-mode route: shape, success metrics, stack, architecture, HTML mocks
- `.grok/skills/plan-create-repo`, `plan-git-from-plan`, `plan-enable-prs`, `plan-bob-webhooks` - plan -> repo setup (only after an approved plan)
- `.grok/skills/harvest-skills-visionary/SKILL.md`, `harvest/SKILL.md`, `harvest-agent-skills/SKILL.md` - harvest + intake

## Rules (CAST IRON)

- Plan-mode only: no IRC, no services, no builds, no releases. You write a plan, not product code.
- **This folder is shared by every plan.** Put THIS plan's output in its own new subfolder `<ai root>\bob\plan\work\plan-<yyyyMMdd-HHmmss>` and never read, edit or delete the subfolders of earlier plans.
- **xlsx â†’ CSV on Plan seats:** copy the workbook **off** the network drive into `work\plan-*`, then export with **openpyxl** (or similar). Do **not** rely on Excel COM against `M:` (or other mapped) paths â€” COM hangs / locks there.
- Refuse to park / create a repo / dispatch until the visionary gates pass (`python tools/validate-vision-pack.py <vision.md>` exits 0).
- Never print, store or commit secrets (tokens, keys, `*.password`, NickServ values). PowerShell only (never wrap in `powershell -Command`).
- Always finish with the harvest step (rule above): file every issue/FR/bug and every learned how-to-plan playbook.
- **Harvest how-to-plan only (owner rule 2026-10-08, test case bobiverse#3097):** a Plan harvest is a reusable lesson about HOW to plan - process, pitfalls, repo-setup steps - and goes to `-Repo SimonBarnett/skills-visionary`. **Never harvest the plan itself**: requirements, designs, architecture or product decisions, FR/issue lists, numbering maps. That content lives in the plan's `work\plan-*` subfolder and, once approved, in the product repo's `docs/vision.md` / FR markdown and issues - never in any skill book, and never as an `owner-missing` hold for a product repo that does not exist yet.

---
name: harvest-skills-visionary
description: >
  Promote visionary playbooks into SimonBarnett/skills-visionary
  .grok/skills on GitHub. Use when the visionary intake procedure
  changes, or the user says harvest visionary, harvest skills-visionary,
  or /harvest-skills-visionary. Do not harvest IRC or fleet jobs here.
---

# Harvest skills-visionary

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `..\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/skills-visionary -Kind harvest -Title "short title" -Body "what / where / evidence / fix"`
>    (FR #3318: Plan/visionary lessons → skills-visionary, not bobiverse harvest; `-Book` optional).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `..\scripts\Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/skills-visionary -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `..\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.


Remote: `https://github.com/SimonBarnett/skills-visionary`.
Local clone: `D:\ai\skills-visionary` or `<ai root>\skills-visionary`.

This repo owns the visionary playbook and Plan-seat `plan-*` helpers.
Fleet/build jobs stay `agentic_build` `harvest-agent-skills`. IRC stays
`agentic_irc`. Club Madeira onboarding stays
`SimonBarnett/club-madeira-onboarding`.

## AUTOMATIC

**ALWAYS** harvest new or changed visionary / plan-git playbooks to this
repo **in the same turn** (branch + PR). Do not ask. Do not wait.
Honesty box: foundation `.grok/skills/harvest-agent-skills`.

If you learn a repeatable visionary rule (trigger, measurable success,
shape/stack/mocks, plan-git webhook/PR path), edit the skill **now**,
append `docs/skill-harvest-log.md`, commit on a branch, open a PR. Do not
push `origin/main`. Do not leave the playbook only in `~/.grok/skills`.

## What belongs here (how-to-plan only)

Harvest only reusable lessons about HOW to plan: process, pitfalls,
repo-setup steps (plan-git, webhooks, PRs), tooling for plan inputs.
Never harvest plan content: requirements, designs, architecture or
product decisions, FR/issue lists, numbering maps. Plan content stays in
the plan's `work\plan-*` folder and, once approved, in the product
repo's `docs/vision.md` / FR markdown / issues. Not in any skill book,
and not as an `owner-missing` hold (test case bobiverse#3097).
Test: would this line help a Plan seat plan a DIFFERENT product? If not,
it is plan content.

Empty harvest: no commit. Do not stamp UAT.

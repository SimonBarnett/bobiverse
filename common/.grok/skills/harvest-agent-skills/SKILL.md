---
name: harvest-agent-skills
description: >
  FOUNDATION: harvest playbooks back as PRs to SimonBarnett/bobiverse.
  Use when harvest skills, honesty box, CAST IRON harvest, or /harvest-agent-skills.
  Prefer deterministic scripts over LLM reasoning. Does not dispatch product builds.
github: https://github.com/SimonBarnett/bobiverse
---

# harvest-agent-skills (bobiverse)

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

**Home:** https://github.com/SimonBarnett/bobiverse

You used these skills. You owe this home repo a report (honesty box). Silence after a useful session is a breach.
Promote learned install/maintain procedures as PRs. Prefer scripts. No main pushes for harvest.

## When you MUST report

1. You learned a **repeatable** procedure (trigger + steps + owner) not already in the book.
2. A skill was **wrong, incomplete, ambiguous, or token-wasteful**.
3. You hit a **bug**, gap, or missing tool that a deterministic script should own.
4. You invented a workaround that should become a skill or a code change.

Empty harvest (nothing new, nothing broken): no empty PR. That is the only quiet case.

## How to report (strict order)

1. **Playbook / fix with write access** -> branch + **pull request** to bobiverse. Never `git push origin main` for harvest.
2. **No GitHub write / API fail** -> intake webhook (`Report-BobiverseIntakeIssue.ps1`) or local `report-outbox/` retry (`Invoke-BobiverseHarvest.ps1 -Flush`).
3. **Bugs / FRs without a ready patch** -> intake `kind: issue|fr` (labels `via-intake`; FR also `feature-request` / `needs-mrb1`).
4. Prefer `.\scripts\Invoke-BobiverseHarvest.ps1` / `Report-BobiverseIntakeIssue.ps1` over free-form chat.

## Where to put lessons

| Area | Path |
|------|------|
| Jeeves / Ergo host / BobJeeves cutover / DPAPI | `jeeves/.grok/skills/bobiverse-jeeves/SKILL.md` (and siblings) |
| Bob ear / tray / worker / plan | `bob/.grok/skills/bobiverse-bob*/SKILL.md` |
| Airc console | `airc/.grok/skills/bobiverse-airc*/SKILL.md` |
| Shared fleet ops / harvest | `common/.grok/skills/` |
| Operator checklist | `docs/post-install.md` / product `docs/` |
| This harvest index | `common/docs/skill-harvest-log.md` |
| Pre-bobiverse historical harvest notes | `docs/archive/*/docs/skill-harvest-log.md` (read-only) |

Live siblings that still take product FRs: `SimonBarnett/skills-visionary`, `SimonBarnett/agentic_fomprep`. Archived repos (`agentic_build`, `agentic_irc`, `gh-Jeeves`, `AgentMonitor`, `bob-design-uat`) are **not** intake targets — see `docs/ARCHIVED_REPOS.md`.

Branch `harvest/…` or `fix/…` → PR to `main`. Bump `common/VERSION` only when the change must ship in the next MSI pack.

## Token efficiency

- Prefer a **deterministic tool or script** over LLM reasoning when both could finish the job.
- Do not narrate step-by-step tool plans in skills; write the command or script name.
- One home per fact. Point at the owner skill; do not duplicate.
- ASCII in `SKILL.md`. Short triggers in frontmatter `description`.

## Scan then write

1. Diff local installed skills vs repo `.grok/skills/` — promote repeatable playbooks.
2. Run `Invoke-BobiverseHarvest.ps1` / pack skill tests; do not reinvent them.
3. Append a dated line to `common/docs/skill-harvest-log.md` when the lesson is new.
4. Skip one-off incident notes and noisy chat.

## Do not

- Push harvest to `main`.
- Commit "nothing found".
- Force-push, secrets, or live credentials into skills.
- Invent skills from noisy session chat.
- Stamp ready for human UAT from a harvest alone.
- Dispatch product builds under the harvest label.
- File intake against archived superseded repos.
- Spend tokens re-deriving a path a script already encodes.

## Inclusion rule

Every bobiverse product skill book SHOULD keep CAST IRON + a one-line pointer:
`Foundation: harvest-agent-skills (honesty box) -> report back to SimonBarnett/bobiverse.`

## Harvest re-ingestion: the honesty box is not noise

Closed `skill` issues and `Skill harvest` GIVEUP/FR records are evidence, not disposable learning. Repeated records may be deduplicated against a canonical FR/merged PR, but every unique `Lessons:` line must be promoted to its owner book. In this pass, the owner books are the Bob worker/UAT/MRB books, Jeeves commands/monitor, fleet ops, and the shared harvest book; no MSSQL-specific lesson was present, so no skill-dba book was changed.

Workers using these books owe a PR back to this repository. Preserve source issue/PR references in the PR body, keep secrets and private tokens out of books, and do not turn a harvest/GIVEUP record itself into a new FR. The 2026-10-04 promotion covered the closed skill corpus through #1460, including the repeated operational lessons from #1211-#1275 and later BobCallback, resync, UAT, machine-pin, MRB, worker-outbox, and monitor records.

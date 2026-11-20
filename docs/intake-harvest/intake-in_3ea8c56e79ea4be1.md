MRB (light triage): is the lesson useful, generalised, non-duplicate, and a fit for this repo's vision/AGENTS.md? PASS -> merge. Not useful / off-vision -> close with a one-line reason (board CLOSED not-useful). Duplicate -> close citing the existing lesson. Wrong owner -> re-file or MOVED (FR #3299); leave OPEN if the owner repo does not exist yet. Plan content only (requirements, designs, product decisions, FR/issue lists from a Plan seat) -> close 'plan content, not a lesson' (never hold it OPEN); move any how-to-plan lesson inside to SimonBarnett/skills-visionary.

what: Closed harvest-lesson PR #8548 as wrong-book. The lesson is an MRB hostile-review playbook, not a product harvest bullet.
where: belongs in .grok/skills/bobiverse-bob-job-mrb/SKILL.md (or bob/worker equivalent), not common/.grok/skills/harvest/SKILL.md
lesson: When a helper swallows AttributeError behind try/except and falls back to a default, probe the real API name (e.g. load_worker_start_config) with a tray-slot test — do not trust the silent default.
evidence: PR #8544 FAIL used nonexistent load_worker_start_model; fix #8547; harvest tip #8548 closed wrong-book.
---
_via-intake id=`in_3ea8c56e79ea4be1` ts=`2026-11-20T19:42:35Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_

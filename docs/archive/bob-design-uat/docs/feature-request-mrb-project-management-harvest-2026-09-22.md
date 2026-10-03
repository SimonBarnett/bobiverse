<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/feature-request-mrb-project-management-harvest-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: harvest MRB / project-management playbooks

**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/49  
**Date:** 2026-09-22  
**Repo:** `SimonBarnett/bob-design-uat`  
**Source:** issue #49 — harvest best-practice project management for engineering MRBs.

## Problem

Design-UAT product work uses GitHub FRs, BT0, and hostile MRB on each issue.
Agents need a **home skill on this repo** for intake → build → evidence → MRB
chairing, without copying the full fleet loop from `agentic_build`.

## Critique

| | |
|--|--|
| **Good** | `bob-hostile-mrb`, `bob-job-loop`, `harvest-agent-skills` on `agentic_build`. |
| **Bad** | #49 had body-only intake; no skill path for design-uat MRB PM. |
| **Ugly** | Workers stamp UAT or implement unrelated FRs inside a FIX. |

## Ask (MUST)

1. Ship `.grok/skills/mrb-project-management/SKILL.md` — engineering MRB **project
   management** for this product repo (intake, plan, worker PR, BT0 evidence,
   Bob chairs MRB on the FR issue). **Defer** verdict/merge ritual to
   `bob-hostile-mrb` on `SimonBarnett/agentic_build` (link, do not duplicate).
2. `tools/Install-DesignUatSkill.ps1` installs this skill with the design-uat
   companions.
3. `tools/Validate-DesignUatSkill.ps1` (BT0) requires this FR file, the skill
   file, and key needles (`mrb-project-management`, `bob-hostile-mrb`,
   `feature-request`, BT0).
4. `design-uat` and `docs/functional-spec.md` cross-link `mrb-project-management`.
5. `docs/build-and-test-plan.md` adds definition of done for issue #49.

## Acceptance

| ID | Criterion |
|----|-----------|
| A-H1 | Skill path exists; YAML `name: mrb-project-management`. |
| A-H2 | Procedure: park FR (`docs/feature-request-*.md` + issue), read plan, worker PR with `#n` in title, paste BT0 on PR/MRB, Bob chairs MRB on FR issue. |
| A-H3 | Skill points at fleet `bob-hostile-mrb` / `bob-job-loop`; does not re-home merge policy. |
| A-H4 | Install + BT0 green; no `password=` / API key assignments in git. |
| A-H5 | Workers MUST NOT post ready for human UAT as authority (Bob only). |

## MUST NOT

- Duplicate `bob-hostile-mrb` body into this repo.
- Implement inside a golden-fixture (#3) FIX.
- Push `main` or merge own PR.
- Second-take closed scope on #2 / #3 / #6 / #7 / #8.

## Out of scope

- Fleet dispatcher scripts (`Start-BobBuildLoop.ps1`, etc.) — stay on `agentic_build`.
- Harvesting IRC playbooks (`agentic_irc`).

<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/feature-request-design-uat-skill-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: design-uat skill for Bob visual UAT

Date: 2026-09-22
Issue: https://github.com/SimonBarnett/bob-design-uat/issues/1
Repo: https://github.com/SimonBarnett/bob-design-uat

## Ask (Simon, #agentic_irc)

New repo for a design skill. Bob will use this for UAT. Need to examine images for:

- spelling mistakes
- hallucinations
- UI fuck-ups
- pixel-perfect UI
- check the original briefs and pick the nits

When the repo exists, anyone can FR it.

## Gap vs tree (P0)

| Area | Before | After P0 |
|------|--------|----------|
| Skill | Missing | `.grok/skills/design-uat/SKILL.md` with G1–G3 |
| Validator | Missing | `tools/Validate-DesignUatSkill.ps1` (BT0) |
| Reports | Ad hoc | `docs/templates/design-uat-report.md` |
| Fixtures | — | P1 (#3) / P2 (#5) follow-on PRs |

P0 does **not** ship golden/adversarial fixture packs (#3, #5).

## Locked

- Skill path: `.grok/skills/design-uat/SKILL.md`
- Bob chairs UAT. Workers do not stamp ready-for-human-UAT.
- No secrets in git. No live PINs/PSKs.
- Do not second-create this repo.

## Traceability (issue #1 → acceptance)

| FR MUST | Spec | Acceptance |
|---------|------|------------|
| G1–G3 visual gates | L4 | A1 |
| Report + gate tags | L5 | A2 |
| BT0 validator | L9 | A3 |
| Build plan BT0–BT2 | L8 | A4 |
| This doc + issue #1 | L8 | A5 |

## Unknown

- Golden fixture pack: #3 (P1).
- Adversarial pack: #5 (P2).
- OCR engine details: U1 in functional spec.

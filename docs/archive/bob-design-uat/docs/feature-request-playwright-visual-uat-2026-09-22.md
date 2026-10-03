<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/feature-request-playwright-visual-uat-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Playwright visual capture for design-uat

**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/57  
**Parked:** 2026-09-22 by MRB of #3 (SHA ba557696) ÔÇö issue had no intake doc and no `feature-request` label.  
**Repo:** SimonBarnett/bob-design-uat  
**Source:** issue #57 as filed: "Should have playwright skills" / "Needs to be able to test visually."

## Intent

Give design-uat a **Playwright** companion so Bob can capture real page stills (routes, viewports, states) and then score those PNGs with existing G1ÔÇôG3. This FR is capture + skill home, not a second golden pack.

## Gap vs current tree

| Area | Now | Residual |
|------|-----|----------|
| Visual score | `design-uat` G1ÔÇôG3 on supplied PNG/JPG/WebP | No browser capture. Agents paste screenshots by hand. |
| Companions | `pdf-design`, `illustrator-design`, `graphics-design` on `main` | No Playwright / live-route skill. |
| Fixtures | `fixtures/<case>/` golden pack (#3) | Static stills only. No route/viewport capture cases. |

## MUST

1. Ship `.grok/skills/playwright-design/SKILL.md` (name `playwright-design`).
2. Skill captures authorized routes/viewports/states to PNG, then **defers scoring to `design-uat` G1ÔÇôG3**.
3. MUST NOT stamp ready for human UAT. Bob chairs that stamp.
4. BT0 requires the new `SKILL.md` and needles (`playwright-design`, pointer to `design-uat`).
5. `tools/Install-DesignUatSkill.ps1` installs the new skill with the others.
6. Docs: this FR + a Related-skills line in `docs/functional-spec.md`.

## MUST NOT

- Second-take #2 / #3 / #6 / #7 / #8 / #29 companions.
- Implement this inside a golden-fixture (#3) FIX or MRB job.
- Push `main` or merge own PR.
- Commit `password=` / `XAI_API_KEY=` assignments.
- Hit live customer URLs or capture PII.

## Acceptance

| ID | Check |
|----|--------|
| A-P1 | Skill path exists with YAML `name: playwright-design`. |
| A-P2 | Procedure: capture stills, then run design-uat G1ÔÇôG3. No worker UAT stamp. |
| A-P3 | Install copies the skill. BT0 fails if it is missing. |
| A-P4 | `design-uat` lists the companion. No secrets in git. |

## Out of scope

- Replacing the #3 golden fixture pack.
- Figma API (U2).
- Inventing product routes not in the brief.

## Park only until dispatched

Issue #57 is the home. Label `feature-request`. Do not implement in the #3 MRB.

<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/functional-spec.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Functional spec: design-uat skill (LOCKED)

**Product:** `SimonBarnett/bob-design-uat` — fleet agent skill for **visual** UAT before Bob stamps human UAT.

**MRB home:** https://github.com/SimonBarnett/bob-design-uat/issues/1  
**Chair:** Bob only for human UAT stamp and MRB merge policy (`bob-hostile-mrb`).

## LOCKED (Simon #agentic_irc — Bob UAT design skill)

| ID | Requirement |
|----|-------------|
| L1 | Skill path: `.grok/skills/design-uat/SKILL.md` with YAML `name: design-uat`. |
| L2 | Triggers: visual UAT, design UAT, screenshot/mockup review, pixel-perfect UI, spelling on images, design nits, `/design-uat`. |
| L3 | Inputs: **brief** (issue, spec, FR md, yaml excerpt, or supplied PDF) plus **artifacts** (PNG/JPG/WebP, Figma exports, PDF pages as images). |
| L4 | **Three visual gates** (issues #2, #6–#8): **G1** OCR spelling vs brief/glossary; **G2** layout-delta vs brief (px/hex, pixel-perfect enumeration, overlapping-element detection when brief requires non-intersecting regions — #71); **G3** invented chrome/copy/imagery not in brief = hallucination. Also apply layout/contrast/a11y nits and brief fidelity (missing/extra states) under G2/G3 as applicable. |
| L5 | Output: structured report from `docs/templates/design-uat-report.md` plus gate-tagged nit rows (`G1`\|`G2`\|`G3`). Verdict section is **evidence only** — no `ready for human UAT`. |
| L6 | Workers: `FAIL`, `PASS-nits candidate`, or `candidate PASS-UAT, Bob stamp required` only. **Bob** stamps ready for human UAT. |
| L7 | No secrets in git. Do not commit `password=` or API key **assignments** (instructional warnings OK). |
| L8 | Repo docs: this file, `docs/feature-request-design-uat-skill-2026-09-22.md`, `docs/build-and-test-plan.md`. |
| L9 | `tools/Validate-DesignUatSkill.ps1` exits 0 when structure checks pass (BT0). |
| L10 | `.github/workflows/bt0.yml` runs BT0. `docs/expected-nits.schema.md` locks YAML shape for #3/#5. Skill has severity rubric + per-image walk. |
| L11 | Golden + adversarial fixtures (#3, absorbed #5): each case has brief + PNG + `expected-nits.yaml`; clean control is zero nits. |

## MUST NOT

| ID | Rule |
|----|------|
| N1 | Push `main` or merge own PR. |
| N2 | Post `ready for human UAT` or final `PASS-UAT` (Bob only). |
| N3 | Invent product requirements not in the brief. |

## UNKNOWN

| ID | Item |
|----|------|
| U1 | OCR engine / language packs (Phase 0: agent vision + report). |
| U2 | Figma API integration. |
| U3 | G2 tolerance if Simon waives strict pixel-perfect. |
| U4 | Brief glossary format. |

## Acceptance IDs

| ID | Acceptance |
|----|------------|
| A1 | Skill lists G1–G3 procedure and L6 verdict rules. |
| A2 | Report template exists and matches skill output. |
| A3 | Validator passes on repo tree (BT0). |
| A4 | Build-and-test plan documents BT0–BT2 and fixture phases P1–P2. |
| A5 | Feature-request doc links issue #1 and maps MUSTs to A1–A4. |
| A6 | Severity rubric + per-image walk in skill; BT0 CI workflow present. |
| A7 | G1 fail-closed (blocker), G3 full inventory (`in_brief` / `NOT_IN_BRIEF`), G2 `delta_px`/`delta_hex` in schema + skill (#6 #7 #8). |
| A8 | Fixture pack + `Validate-DesignUatFixtures.ps1` (A-F1–A-F4). |

## Related skills (companions)

| Skill | Role |
|-------|------|
| `design-uat` | Product UI screenshots / mocks (this skill) |
| `pdf-design` | PDF / print page stack |
| `illustrator-design` | Illustrator artboards / exports |
| `graphics-design` | Loose graphics packs (PNG/SVG/icons) |
| `playwright-design` | Playwright capture of authorized routes/viewports/states → PNG, optional bbox overlap pass (#71), then G1–G3 (#57) |
| `mrb-project-management` | Engineering MRB PM for this repo (issue #49); hostile verdict on `agentic_build` |

## Related GitHub FRs

#1 skill (MRB home), #3 golden fixtures, #5 adversarial fixtures, #6 G1 spelling, #7 G3 hallucination, #8 G2 pixel deltas; PDF/Illustrator/graphics companions FR (`docs/feature-request-pdf-illustrator-graphics-skills-2026-09-22.md`); Playwright visual capture FR (`docs/feature-request-playwright-visual-uat-2026-09-22.md`, #57); screen layout overlap FR (`docs/feature-request-screen-layout-overlap-2026-09-22.md`, #71); MRB PM harvest (#49, `docs/feature-request-mrb-project-management-harvest-2026-09-22.md`).

## Phase order

| Phase | Deliverable |
|-------|-------------|
| P0 | Docs, skill, template, validator, build plan (this PR) |
| P1 | Golden + absorbed adversarial fixtures (#3 / #5) — this PR |
| P2 | G1/G2/G3 owner FRs #6–#8 (do not second-take) |

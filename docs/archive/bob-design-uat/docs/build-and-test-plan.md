<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/build-and-test-plan.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: design-uat skill

**Date:** 2026-09-22  
**Repo:** SimonBarnett/bob-design-uat  
**FR:** docs/feature-request-design-uat-skill-2026-09-22.md  
**Issue (#1):** https://github.com/SimonBarnett/bob-design-uat/issues/1  
**Issue (#7 G3):** https://github.com/SimonBarnett/bob-design-uat/issues/7 — `docs/feature-request-hallucination-inventory-2026-09-22.md`  
**Issue (#8 G2):** https://github.com/SimonBarnett/bob-design-uat/issues/8 — `docs/feature-request-pixel-perfect-deltas-2026-09-22.md`  
**Issue (#57 Playwright):** https://github.com/SimonBarnett/bob-design-uat/issues/57 — `docs/feature-request-playwright-visual-uat-2026-09-22.md`  
**Issue (#71 overlap):** https://github.com/SimonBarnett/bob-design-uat/issues/71 — `docs/feature-request-screen-layout-overlap-2026-09-22.md`  

## Goals

1. Ship P0: skill, functional spec, FR, report template, validator, this plan (issue #1).
2. Later: golden (#3) and adversarial (#5) fixture packs with expected nit YAML.
3. Keep gates G1–G3 repeatable; Bob chairs MRB on #1.

## Non-goals

- Ready for human UAT stamp (Bob only).
- Push/merge `main` from workers.
- Secret assignments in git.

## Locked constants

| Name | Value |
|------|--------|
| MRB issue | #1 |
| Skill | `.grok/skills/design-uat/SKILL.md` |
| Gates | G1 spelling, G2 layout-delta, G3 invented chrome |
| Clean control | Zero nits (#5) |

## BT0 — Structure (required before MRB)

From repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Validate-DesignUatSkill.ps1
```

**Pass:** exit code `0`. **Evidence:** paste output into PR or MRB comment. Satisfies **A3**. CI: `.github/workflows/bt0.yml` runs the same script on Windows.

Install for local Bob (does not stamp UAT):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Install-DesignUatSkill.ps1
```

Expected nit YAML shape for later fixture PRs: `docs/expected-nits.schema.md`. Do not add fixture images in a #1 keep-building PR.

## BT1 — Skill walkthrough (manual)

1. Open `.grok/skills/design-uat/SKILL.md`.
2. Confirm G1 → G2 → G3 procedure and brief-first intake.
3. Confirm L6/N2: no worker `ready for human UAT`.

**Pass:** MRB agrees **A1**.

## BT2 — Sample report (manual)

1. Copy `docs/templates/design-uat-report.md` outside the repo (do not commit filled report).
2. Fill with a fictional brief + artifact list; tag nits with G1/G2/G3.
3. Verdict uses only FAIL / PASS-nits candidate / candidate PASS-UAT wording.

**Pass:** **A2**.

## P0b — Gate schema (issues #6 #7 #8)

`docs/expected-nits.schema.md` plus skill/template rules (satisfies **A7**):

| Test | Expected |
|------|----------|
| T-S06 | G1 typo is blocker / FAIL (fail-closed) |
| T-S07 | G3 inventory table required (report template + skill `NOT_IN_BRIEF`; BT0 checks) |
| T-S08 | G2 row has delta_px and/or delta_hex |

**T-S08 evidence:** BT0 checks skill `Deltas (#8)`, schema `G2 deltas (#8)`, and report template `delta_px` / `delta_hex` columns.

## P1 — Golden + absorbed #5 fixtures (issue #3)

Tree: `fixtures/<case>/` with `brief.md`, `screenshot.png`, `expected-nits.yaml` (schema in `docs/expected-nits.schema.md`).

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Validate-DesignUatFixtures.ps1
```

| Test | Expected |
|------|----------|
| T-G01 | Misspelling case → G1 **blocker** |
| T-G02 | Layout case → G2 nit with px/hex |
| T-G04 | Overlap case → G2 layout / bbox intersection (#71) |
| T-G03 | Hallucination → G3, `NOT_IN_BRIEF` |
| T-A01 | Wrong hex → G2 |
| T-A02 | 1px pad → G2 nit |
| T-A03 | Invented logo → G3 |
| T-A00 | Clean control → `nits: []` |

## P2 — Gate-owner FRs (#6 #7 #8)

Do not second-take. 23624 lock.

## Definition of done (P0 / issue #1)

- [ ] BT0 green on PR branch
- [ ] PR title includes `#1`
- [ ] Test summary on PR (BT0 output + BT1 checklist)
- [ ] No UAT stamp in PR body
- [ ] Bob chairs MRB on #1

## Definition of done (#7 / T-S07)

- [ ] BT0 green (includes T-S07 report + skill needles)
- [ ] `docs/feature-request-hallucination-inventory-2026-09-22.md` on branch
- [ ] PR title includes `#7`
- [ ] Test summary on PR (BT0 output; T-S07 row)
- [ ] No UAT stamp in PR body
- [ ] Bob chairs MRB on #7 (fixture proof T-G03 stays on #3)

## Definition of done (issue #8 — G2 pixel deltas)

**FR:** `docs/feature-request-pixel-perfect-deltas-2026-09-22.md`  
**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/8  

- [ ] `docs/feature-request-pixel-perfect-deltas-2026-09-22.md` on branch
- [ ] Skill **Deltas (#8)** + schema **G2 deltas (#8)** + report `delta_px` / `delta_hex` columns (T-S08)
- [ ] BT0 green on PR branch (includes T-S07 + T-S08 needles)
- [ ] PR title includes `#8`
- [ ] Test summary on PR (BT0 output + T-S08 note)
- [ ] No UAT stamp in PR body
- [ ] Bob chairs MRB on #8 (fixture proof T-G02 stays on #3)

## Definition of done (issue #2 — three gates)

**FR:** `docs/feature-request-three-gates-2026-09-22.md`  
**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/2  

- [ ] BT0 green on PR branch (includes three-gates FR file)
- [ ] Skill: fail-closed **G1 → G2 → G3**; per-gate PASS/FAIL in report body
- [ ] Report template: gate scorecard section
- [ ] PR title includes `#2`
- [ ] No UAT stamp in PR body
- [ ] Bob chairs MRB on #2

## Definition of done (issue #57 — Playwright visual capture)

**FR:** `docs/feature-request-playwright-visual-uat-2026-09-22.md`  
**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/57  

- [ ] `.grok/skills/playwright-design/SKILL.md` with YAML `name: playwright-design`
- [ ] Procedure: capture stills, then `design-uat` G1–G3; no worker UAT stamp
- [ ] `design-uat` lists `playwright-design` companion; `docs/functional-spec.md` Related skills row
- [ ] `tools/Install-DesignUatSkill.ps1` installs `playwright-design`
- [ ] BT0 green (requires skill file + needles: `playwright-design`, `design-uat`)
- [ ] PR title includes `#57`
- [ ] No UAT stamp in PR body
- [ ] Bob chairs MRB on #57

## Definition of done (issue #71 — screen layout overlap)

**FR:** `docs/feature-request-screen-layout-overlap-2026-09-22.md`  
**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/71  
**BT plan:** `docs/build-and-test-plan-screen-layout-overlap-2026-09-22.md`

- [ ] G2 overlap procedure in `design-uat` and `playwright-design`
- [ ] `fixtures/T-G04-overlap/` + `tools/LayoutOverlap-PlaywrightHook.example.mjs`
- [ ] BT0 green on PR branch (T-G04 + overlap needles)
- [ ] PR title includes `#71`
- [ ] No UAT stamp in PR body
- [ ] Bob chairs MRB on #71

## Definition of done (issue #49 — MRB PM harvest)

**FR:** `docs/feature-request-mrb-project-management-harvest-2026-09-22.md`  
**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/49  

- [ ] `docs/feature-request-mrb-project-management-harvest-2026-09-22.md` on branch
- [ ] Skill `mrb-project-management` + install script + BT0 needles (A-H1–A-H5)
- [ ] BT0 green on PR branch
- [ ] PR title includes `#49`
- [ ] Test summary on PR (BT0 output)
- [ ] No UAT stamp in PR body
- [ ] Bob chairs MRB on #49

## Kickoff (`Start-BobBuild -Goal`)

Read `docs/functional-spec.md`, `docs/feature-request-design-uat-skill-2026-09-22.md`, and
`docs/build-and-test-plan.md`. Implement next open phase (P1 if P0 merged). Open a PR for #1.
Never push main. Never merge. Do not stamp UAT. Do not set an API key environment variable.
PR model: composer-2.5 (or build0.1 / grok-4.5). Never Other Models.

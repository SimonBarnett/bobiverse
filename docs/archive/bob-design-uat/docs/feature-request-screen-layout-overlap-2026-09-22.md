<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/feature-request-screen-layout-overlap-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: Screen layout overlap checks (issue #71)

**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/71  
**Ask (Simon):** Screen layout should be check for overlapping elements.

## Summary

Add design-uat skill/procedure coverage so visual UAT (playwright companions)
flags overlapping UI elements (bbox intersection / axe-adjacent layout checks).

## Gap vs main

Playwright visual UAT exists; overlap/layout collision check is not an
explicit MUST in companion skills.

## MUST

1. Document G2 overlap procedure in `design-uat` and `playwright-design` skills (#71).
2. Ship calibration fixture `fixtures/T-G04-overlap/` and example hook `tools/LayoutOverlap-PlaywrightHook.example.mjs` (no secrets).
3. BT0 requires FR doc, overlap needles, and fixture validator row for T-G04.
4. README + `docs/functional-spec.md` link this FR.
5. MUST NOT stamp ready for human UAT. Bob chairs MRB on #71.

## Acceptance

| ID | Check |
|----|--------|
| A1 | Documented procedure or skill gate for overlapping-element detection. |
| A2 | Example fixture or test hook referenced (no secrets). |
| A3 | Links from README / companion skill index. |
| A4 | Existing BT0/visual paths remain green or explicitly stubbed UNKNOWN. |

Workers do not stamp ready for human UAT.
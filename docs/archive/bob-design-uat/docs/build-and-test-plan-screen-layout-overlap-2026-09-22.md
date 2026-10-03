<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/build-and-test-plan-screen-layout-overlap-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: screen layout overlap (#71)

**Issue:** https://github.com/SimonBarnett/bob-design-uat/issues/71  
**FR:** `docs/feature-request-screen-layout-overlap-2026-09-22.md`

## Steps

1. Survey `playwright-design` and `design-uat` companions — add G2 overlap procedure (#71).
2. Add `fixtures/T-G04-overlap/` + `tools/LayoutOverlap-PlaywrightHook.example.mjs`.
3. Wire README, `docs/functional-spec.md`, `docs/build-and-test-plan.md`; open PR linking #71.

## BT0

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Validate-DesignUatSkill.ps1
```

**Pass:** exit `0` (includes T-G04-overlap fixture checks and overlap needles).

## Definition of done (#71)

- [ ] `design-uat` + `playwright-design` document overlap / bbox intersection under G2
- [ ] `fixtures/T-G04-overlap/` + example Playwright hook on branch
- [ ] BT0 green on PR branch
- [ ] PR title includes `#71`
- [ ] No UAT stamp in PR body
- [ ] Bob chairs MRB on #71

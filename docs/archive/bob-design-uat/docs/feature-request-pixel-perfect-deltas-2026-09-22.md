<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path docs/feature-request-pixel-perfect-deltas-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: pixel-perfect deltas vs brief or mock

Date: 2026-09-22
Issue: https://github.com/SimonBarnett/bob-design-uat/issues/8
Repo: https://github.com/SimonBarnett/bob-design-uat

## Ask

Compare screenshot to brief or supplied mock. Report alignment, spacing, type size, and color deltas in px / hex. Pixel-perfect means those deltas are listed; any unexplained delta is a nit.

## Gap vs tree

| Area | Before #8 PR | After #8 PR |
|------|----------------|-------------|
| G2 px/hex rule | In skill/schema from P0b (#17) | Locked in FR + BT0 T-S08 needles |
| Parked FR | Issue body only | `docs/feature-request-pixel-perfect-deltas-2026-09-22.md` on branch |
| Proof fixture | — | #3 T-G02 (follow-on) |

Do not rewrite G2 semantics. Remaining proof is golden layout case T-G02; tolerance only if Simon locks U3.

## Locked

- Every G2 nit row includes at least one of `delta_px` or `delta_hex` (report + `expected-nits.yaml`).
- Pixel-perfect means deltas are listed, not "looks close".
- No UAT stamp. Bob chairs MRB on #8. No secrets in git.

## Traceability (issue #8 → acceptance)

| FR MUST | Spec | Acceptance |
|---------|------|------------|
| G2 px/hex on every row | L4, L10 | A7 (G2 leg) |
| Report columns | L5 | A2 |
| Schema example | L10 | A7 |
| BT0 T-S08 | L9 | A3 |

## Unknown

- Mock source (brief PDF vs Figma export).
- G2 tolerance if Simon later allows one (U3 in `docs/functional-spec.md`).

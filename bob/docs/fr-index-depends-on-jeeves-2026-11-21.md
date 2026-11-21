# Index: Depends-on preconditions: Plan stamps + Jeeves skip-until-closed

**Repo:** SimonBarnett/bobiverse  
**Date:** 2026-11-21  
**Mode:** park-only anti-omnibus

| ID | Issue | Title | Doc |
|----|-------|-------|-----|
| BOB-D1 | [#8805](https://github.com/SimonBarnett/bobiverse/issues/8805) | Parse Depends-on from issue body | docs/feature-request-depends-on-parse-body-2026-11-21.md |
| BOB-D2 | [#8806](https://github.com/SimonBarnett/bobiverse/issues/8806) | Relative #N uses FR own repo | docs/feature-request-depends-on-relative-hash-repo-2026-11-21.md |
| BOB-D3 | [#8807](https://github.com/SimonBarnett/bobiverse/issues/8807) | Skip offer when any depend OPEN | docs/feature-request-depends-on-skip-offer-open-2026-11-21.md |
| BOB-D4 | [#8808](https://github.com/SimonBarnett/bobiverse/issues/8808) | Offerable when all depends CLOSED | docs/feature-request-depends-on-offerable-when-closed-2026-11-21.md |
| BOB-D5 | [#8809](https://github.com/SimonBarnett/bobiverse/issues/8809) | Fail closed on unresolved refs | docs/feature-request-depends-on-fail-closed-unresolved-2026-11-21.md |
| BOB-D6 | [#8810](https://github.com/SimonBarnett/bobiverse/issues/8810) | Fetch issue body when queue row body empty | docs/feature-request-depends-on-fetch-empty-body-2026-11-21.md |
| BOB-D7 | [#8811](https://github.com/SimonBarnett/bobiverse/issues/8811) | Wire beside fr_hold_reason | docs/feature-request-depends-on-wire-fr-hold-sites-2026-11-21.md |
| BOB-D8 | [#8812](https://github.com/SimonBarnett/bobiverse/issues/8812) | Docs: Depends-on vs hold | docs/feature-request-depends-on-docs-vs-hold-2026-11-21.md |
| BOB-D9 | [#8813](https://github.com/SimonBarnett/bobiverse/issues/8813) | Close or retarget #8754 | docs/feature-request-depends-on-retarget-8754-2026-11-21.md |

## Notes

- Park-only: no bob-job-loop until asked.
- Grammar: `Depends-on: #N` same-repo; `owner/repo#N` cross-repo; `(none)` when empty.
- Distinct from hold / HOLD: stamps (FR #4009).
- Plan-side stamps: skills-visionary VIS-D1..D5 (#147–#151).
- #8754 (backlog-id Depends-on) is superseded by these issue# refs; close via BOB-D9 when D1–D8 land.

# FR-D9 Retarget #8754 to issue-number Depends-on index

GitHub: #8813 (BOB-D9). Refs SimonBarnett/bobiverse#8754. Stays open until D1–D8 land. Docs only.

#8754 asked for a backlog-ID (BOB-N) offer gate. That design is superseded by enforceable issue-number Depends-on stamps. This mirror records the retarget and the deferred-closure condition. Do not close #8754 from this card while any of #8805–#8812 remain open.

## Goal

Retarget #8754 from backlog-ID Depends-on to issue-number `Depends-on:` references tracked by the Depends-on Jeeves index.

Cite the literal index path `bob/docs/fr-index-depends-on-jeeves-2026-11-21.md` and the pinned URL at commit `47649cf4ba886bc49e366cd43b984b5bf9d99cba`:

https://github.com/SimonBarnett/bobiverse/blob/47649cf4ba886bc49e366cd43b984b5bf9d99cba/bob/docs/fr-index-depends-on-jeeves-2026-11-21.md

Grammar: `Depends-on: #N` same-repo; `owner/repo#N` cross-repo; `(none)` when empty.

## Deliverables

- #8754 body cites `bob/docs/fr-index-depends-on-jeeves-2026-11-21.md` (S1 measurement).
- Comment + Closes plan on #8754: #8754 stays open until #8805–#8812 are all closed with their work on main; then close via BOB-D9.
- This docs mirror on main for reviewers and later agents.
- D1–D8 issue list with one-line scope each:
  - #8805 BOB-D1: Parse Depends-on from issue body
  - #8806 BOB-D2: Relative #N uses FR own repo
  - #8807 BOB-D3: Skip offer when any depend OPEN
  - #8808 BOB-D4: Offerable when all depends CLOSED
  - #8809 BOB-D5: Fail closed on unresolved refs
  - #8810 BOB-D6: Fetch issue body when queue row body empty
  - #8811 BOB-D7: Wire beside fr_hold_reason
  - #8812 BOB-D8: Docs: Depends-on vs hold

## Testable

- This mirror contains `fr-index-depends-on-jeeves-2026-11-21.md`.
- This mirror contains pinned commit SHA `47649cf4ba886bc49e366cd43b984b5bf9d99cba`.
- This mirror lists #8805 #8806 #8807 #8808 #8809 #8810 #8811 #8812.
- This mirror contains the wording that #8754 stays open until D1–D8 land.
- No line starts with a closing keyword that names #8754.
- No line-anchored `HOLD ...:` stamp.

## Out of scope

- D1–D8 implementation (gate code in Jeeves / gitclaim).
- VIS-D1–D5 Plan stamps (skills-visionary).
- PR #8787 (merged backlog-ID design; unchanged by D9; owner decides Refs vs leave).
- Cross-repo issue-state cache TTL (UNKNOWN in the vision pack).

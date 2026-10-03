<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-harvest-skills-as-pr-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: skill harvest as a PR, not a commit to main

**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/214
**MRB board (FAIL):** https://github.com/SimonBarnett/agentic_build/issues/217
(prior scored SHA `6d567f6`; FIX PR https://github.com/SimonBarnett/agentic_build/pull/218)

**Ask (Simon `#bobiverse` 2026-09-23):**
update builder skills - send skills harvest as a PR, NOT a commit to main.

## LOCKED

1. Useful harvest commits go on a branch and open a PR. Do not
   `git push origin main` for skill harvest.
2. Empty harvest: no commit (unchanged).
3. Workers already never push main. Harvest matches that.
4. No UAT stamp.

## Gap

Closed on FIX PR after MRB #217: `-Success` must not name `origin/main` as
done (open PR or empty harvest log only).

## Acceptance

- A1: Owner skill + harvest script say PR, not main.
- A2: Harvest log notes this rule.
- A3: No UAT stamp.

<!-- ARCHIVED COPY - source: SimonBarnett/gh-Jeeves @ 4ff29b5, path docs/feature-request-k1-chair-bored-fr175-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #175 / K1: chair handles !bored (blocks gate)

**Issue:** https://github.com/SimonBarnett/gh-Jeeves/issues/175

## Outcome (SoT)

**Resolved by FR #106:** Jeeves owns worker `!bored` in `#{machine}` and posts
**one assign line**. Ear OFFER / git-claim / ASSIGN multi-wake paths stay forbidden.

Tests: `tests/test_k1_fr175_chair_bored.py` lock `chair_handles_bored()`, assign
egress, and static scan for legacy chair claim handlers.

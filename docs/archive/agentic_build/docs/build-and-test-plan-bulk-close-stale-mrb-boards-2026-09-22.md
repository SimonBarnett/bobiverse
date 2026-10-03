<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-bulk-close-stale-mrb-boards-2026-09-22.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan: bulk-close stale MRB boards (#140 / #170)

1. Rewrite `tools/Close-BobMrbPassedIssues.ps1` with mandatory `-Repo` +
   `-MergedPrUrl`, merge gate, PR URL in comments, this-PR scoping.
2. Off-DEV Test-Pack `BT170a`–`BT170d` using Fake-Gh.
3. Point intake docs at issue #140 / FAIL #170.

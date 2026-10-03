<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bulk-close-stale-mrb-boards-2026-09-22.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: bulk-close stale MRB PASS-nits boards (one-shot)

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**GitHub issue / chair:** https://github.com/SimonBarnett/agentic_build/issues/140  
**FAIL boards:** #165, #170  
**Related:** #118 PASS-nits close ritual (`Close-BobBuildLoopFinished`)

## Ask

One-shot `Close-BobMrbPassedIssues.ps1` closes finished PASS-nits boards for a
**already-merged** worker PR, with comments that name that PR URL.

## Acceptance (FAIL #170)

1. `-Repo` is mandatory with **no** default of `SimonBarnett/agentic_irc`.
2. `-MergedPrUrl` is mandatory; refuse to close unless `Test-BobGhPrIsMerged`.
3. Every close comment includes the merged PR URL; never claim merged otherwise.
4. Scope to OPEN PASS boards that name that PR; FAIL boards only for those
   PASS slugs; FRs listed in those PASS bodies. Do not close unfinished live
   boards via historical closed PASS.
5. Off-DEV Test-Pack (Fake-Gh): close set, comment has URL, open PR refuses,
   missing `gh` fails.
6. Do not implement Watch-IrcTsr / #163 on this closer.

## Non-goals

- Replacing the loop driver closer (`Close-BobBuildLoopFinished` / #118).
- Auto-merging PRs (`Merge-BobMrbPassOpenPrs.ps1` stays separate / gated).

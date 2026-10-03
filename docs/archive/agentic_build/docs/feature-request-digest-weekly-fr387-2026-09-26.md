<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-digest-weekly-fr387-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #387: digest weekly vs local Get-BobWeeklyRemaining

**Issue:** https://github.com/SimonBarnett/agentic_build/issues/387

## Root cause

`Write-BobIrcStatus` already POSTs `weekly` + `period_end` on `op=merge`.
gh-Jeeves `coerce_machine` / merge ignored those fields, so GET digest for
marchhare had workers but no weekly while local xAI weekly was 63%.

## Fix

- gh-Jeeves: persist `weekly` + `period_end` (+ do not wipe pcent with `{}`)
- This repo: document in `bob-digest-webhook`

## PR

https://github.com/SimonBarnett/gh-Jeeves/pull/174

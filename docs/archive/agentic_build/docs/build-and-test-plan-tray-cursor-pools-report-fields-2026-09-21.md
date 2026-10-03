<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-tray-cursor-pools-report-fields-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: tray Cursor pools + !report fields

**Date:** 2026-09-21
**FR:** `docs/feature-request-tray-cursor-pools-report-fields-2026-09-21.md`
**Issue:** https://github.com/SimonBarnett/agentic_build/issues/91
**Sister:** https://github.com/SimonBarnett/agentic_irc/issues/36
**Profile:** generic
**Do not:** Stop-ScheduledTask BobFleet-*, invent `?` jobs, collapse seats into one bar, push `main`, MRB in-session.

## Work tree

Branch `work/<jobId>` off `main`. Open a PR. Never push `main`.

## Steps

1. Read `config/bob-seats.json`, `Get-BobTrayHover.ps1`, `Watch-BobTray.ps1`, `bob-fleet-tray` skill.
2. Split the single Cursor Models strip into one bar per seat/pool the usage helpers already return. If a pool has no % yet, show the bar with `n/a` — do not hide it.
3. Extend hover job lines to print `state repo sha model description run_time` from local build packets first (kills `grok.exe ?` when the job file has repo/sha).
4. Add an optional ingest of irc digest JSON (`!bobiverse` / peer file) when present; same line format. Skip live IRC in Test-Pack.
5. Fixtures in Test-Pack: ≥2 Cursor bars; START line contains sha + description; empty machine `no jobs`.
6. Update `bob-fleet-tray` skill. Comment #91 + irc #36 with the PR URL.

## Prove

```powershell
powershell -NoProfile -File .\tools\Test-Pack.ps1
```

Fake-Grok only. No live bots.

## Done when

PR open, Test-Pack green, wait for handed-off MRB. FAIL → FIX PR. PASS-nits merges. Only Bob stamps UAT.

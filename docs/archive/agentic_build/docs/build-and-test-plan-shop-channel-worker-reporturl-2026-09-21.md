<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-shop-channel-worker-reporturl-2026-09-21.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: shop JOIN + worker nick + write-only `reportUrl`

**Date:** 2026-09-21  
**Repo:** SimonBarnett/agentic_build  
**FR:** `docs/feature-request-shop-channel-worker-reporturl-2026-09-21.md`  
**Issue:** #124  
**Sister protocol:** agentic_irc #46  

## Goals

1. `Watch-Bobiverse` / `Install-BobIrc` `irc_agent` JOINs `#bobiverse` and local `#<machine>` shop.
2. `Start-BobWorkerIrcAgent` spawns shop-only `w-<short>-<pid>` (never `#bobiverse`).
3. `config/bobiverse.json` `reportUrl` + change-only POST from `Write-BobIrcStatus` (#141); no HTTP GET; secrets via `X-Bob-Secret` only.

## Test-Pack (hermetic)

- `BT0l24 shop channel worker reportUrl`: shop/builder channel helpers, `reportUrl` present, POST-only webhook source, Watch/Install source checks, optional `start_worker_irc_agent.py --dry-run`, docs/skill shop text.

## Definition of done

- PR against `main` (never push `main`). Test-Pack green.
- Open PR; Bob chairs MRB on #124. No worker UAT stamp.

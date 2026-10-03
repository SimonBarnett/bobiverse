<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-digest-webhook-producer-change-only-2026-09-21.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: change-only digest webhook from `Write-BobIrcStatus`

**Date:** 2026-09-21  
**Repo:** SimonBarnett/agentic_build  
**FR:** `docs/feature-request-digest-webhook-producer-change-only-2026-09-21.md`  
**Issue:** #141  
**Sister consumer:** agentic_irc #73  

## Goals

1. `Write-BobIrcStatus` POSTs `config/bobiverse.json` `reportUrl` on real peer
   delta only (skip `lastSeen`-only ticks).
2. Payload: `op=merge`, machine fields per sister `bobreport` merge (no secrets
   in JSON; `X-Bob-Secret` from env/file only).
3. `Watch-Bobiverse` unchanged: not the chair; no `BOB DIGEST` / POINT from
   this path.

## Test-Pack (hermetic)

- `BOB_DIGEST_WEBHOOK_CAPTURE` file receives POST bodies (no live HTTP).
- Two `Write-BobIrcStatus` ticks with stable fuel/jobs → zero capture lines.
- Cursor usage fixture change between ticks → exactly one capture line; repeat
  tick → still one line.

## Definition of done

- PR against `main` (never push `main`). Test-Pack green.
- Open PR; Bob chairs MRB on #141. No worker UAT stamp.

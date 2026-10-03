<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: ingest tray-complete `!bobiverse` into systray peers

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Sister (protocol):** https://github.com/SimonBarnett/agentic_irc  
`docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md`  
**Related:** #26 channel-talk + tray pull, #91 cursor pools, irc #36  
**Raised by:** Simon (2026-09-21 ~23:17 BST)  
**UAT + hostile MRB owner:** Bob  

## Problem

Simon: **a bob has to be able to `!bobiverse` and see all the information
required for the Bob systray.**

Watch already polls `!bobiverse` (~120s) and calls `Import-BobIrcTrayPull`,
but that importer only accepts `BOB TRAY v1` kv lines. Chair whispers today
are mostly `BOB DIGEST v1` presence JSON (online / workers / working_on).
Tray fields (`weekly`, `period_end`, `cursor_label`, job repo/sha/model)
stay local-only via `Write-BobIrcStatus`, so peer boxes cannot paint a full
card from IRC alone.

## LOCKED

1. **Do not gut the systray.** Keep **all data already on the card**.
   Do not redesign TipForm down to today’s thin presence digest.
2. **Only additive UI:** separated **Cursor quota** bars per seat
   (issue #91). Everything else that is already there stays.
3. **Refresh = `!bobiverse` JSON.** Watch / tray poll asks `!bobiverse`,
   ingests `BOB DIGEST v1` JSON into `bob-peers` (and cursor pool cache).
   That is the fleet refresh path — not POINT, not “drop fields we
   cannot map yet.”
4. After one pull, peers hold everything `Get-BobTrayHover` needs for
   today’s tiles **plus** `cursor_pools`.
5. Job lines: never publish `?` when digest has repo/sha.
6. Test-Pack hermetic: fake DIGEST whisper → peers → hover shows full
   card surface + separated Cursor bars; no live Ergo.
7. Skill `bob-fleet-tray`: freshness = `!bobiverse` JSON pull; card
   content = existing surface + #91 pools.

## Gap vs tree

| Current | Wanted |
|---|---|
| Rich local paint; thin IRC pull | Pull JSON = **full card dataset** |
| Risk of shrinking UI to match digest | **UI stays full**; digest grows to match UI |
| #91 separated Cursor bars | Keep that; wire via same JSON refresh |
| `Import-BobIrcTrayPull` = `BOB TRAY v1` only | Ingest DIGEST JSON → peers |

## Acceptance

1. Fixture DIGEST → hover paints no less than today’s card + separated
   Cursor bars; non-`?` job line when sha present.
2. Live: recycle Watch only; bob `!bobiverse` refreshes tray without POINT.
3. PR only; Bob stamps UAT.

## Non-goals

- Gutting tray fields to fit a small digest.
- `Install-BobFleet` / scheduled-task churn.
- HTTP GET digest.

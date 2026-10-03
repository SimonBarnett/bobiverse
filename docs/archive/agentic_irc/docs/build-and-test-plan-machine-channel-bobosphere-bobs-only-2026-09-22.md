<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-machine-channel-bobosphere-bobs-only-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan — machine shop + bobosphere bobs-only + Jeeves all rooms

**FR:** docs/feature-request-machine-channel-bobosphere-bobs-only-2026-09-22.md  
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/100  
**PR:** https://github.com/SimonBarnett/agentic_irc/pull/99

## Build

1. Land channels_for_nick / parse_talk_seat_nick / chair_channels.
2. irc_agent.py --chair uses chair_channels().
3. Start-TalkSeat.ps1 default #{machine},#agentic_irc.
4. Sync src/moot_thin/VERSION with AIRC_THIN_VERSION (CI gate).

## Test

1. pytest tests/test_bobreport.py::test_channels_for_nick — talk seats strip #bobiverse; chair_channels lists fleet + four shops.
2. pytest tests/test_bobiverse_talk.py::test_chair_answers_bobiverse_builder_silent — chair.channels is fleet+shops.
3. Full pytest -q green (incl. moot_thin version sync).
4. Manual: recycle talk seats; NAMES on #{machine} shows bob-* + talk seats; talk seats absent from #bobiverse.
5. ionos: recycle Jeeves; present in #bobiverse and every shop.

## Done when

PR merged; issue #100 closable after PASS-nits MRB; Jeeves recycled on ionos.

<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-digest-bob-url-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: digest on bob.ntsa.uk (issue #174)

**Repo:** SimonBarnett/agentic_irc  
**Issue:** #174  
**Shape:** service (LOCKED) — HTTP digest read + metrics webhook writer; IRC `!bobiverse` removed.

## Ultimate objective

Bob (and any fleet box) reads fleet digest and shared account metrics from a public URL on `bob.ntsa.uk`. Machines push local xAI + Cursor meters every two minutes; the digest keeps the **lesser** remaining % as source of truth. Nobody uses `!bobiverse` to refresh or read the digest.

## Shape

LOCKED

Primary: service

HTTP digest read endpoint + gated webhook writer + long-running metrics PS1. No UI mocks.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Public digest GET | `GET /bob/v1/digest` returns JSON digest without secret | `tests/test_bobcallback.py` + offline handler | GET still 404/405 or requires secret |
| S2 | `!bobiverse` gone | Chair and bob-* ignore the command; no periodic IRC pull | `tests/test_bobiverse_talk.py`, `tests/test_bobiverse_pull.py` | Any PRIVMSG `!bobiverse` pull or digest whisper answer |
| S3 | HTTP pull | bob-* refresh local digest via GET digest URL | pull test with mocked HTTP | Still sends `!bobiverse` on IRC |
| S4 | Lesser metrics SoT | Shared Cursor pool remaining = min across machines | `tests/test_bobreport.py` cursor_pools case | Max / first-writer wins |
| S5 | 2-min metrics PS1 | `tools/Watch-BobDigestMetrics.ps1` posts weekly + pcent merge every 120s | script present; dry-run builds payload | Missing script or wrong interval |

## Gap vs current tree

- `bobcallback` is write-only; GET `/bob/v1/digest` returns 404.
- bob-* periodically `PRIVMSG #bobiverse :!bobiverse`; Jeeves answers with whisper chunks.
- `_best_machine_pcent_for_pool` picks the **max** remaining.
- No long-running PS1 that posts box usage to the webhook.

## Out of scope

- Changing Ergo TLS / IRC join rooms.
- UAT stamp.
- Putting secrets in the digest (none belong there).

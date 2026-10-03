<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-systray-digest-help-2026-09-23.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: systray TipForm (#179 on agentic_irc)

**Repos:** SimonBarnett/agentic_build (tray code). Tracking issue: SimonBarnett/agentic_irc#179.  
**Shape:** app (LOCKED) — Windows NotifyIcon TipForm.

## Ultimate objective

The Bob Fleet systray TipForm shows Cursor quota groups with a `?` help tip naming the group and which models sit in that pool, always prints **0%** when remaining is zero (never `n/a`), and refreshes Grok machine meters from the public digest HTTP GET once a minute.

## Shape

LOCKED

Primary: app

TipForm + Watch-BobTray poller. No new website.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Per-group `?` | Each Cursor quota row has `?` tooltip with group description + included models | Test-Pack / offline tooltip helper | Only section-level help or empty tip |
| S2 | Zero is 0% | remaining_pct 0 → label `0%`, bar known | Test-Pack assert | Label `n/a` or unknown paint for 0 |
| S3 | Digest GET 1m | Grok tiles fed from `GET` digest URL; refresh ≤60s | Read-BobReportDigest HTTP path + PollSec | Still IRC `!bobiverse` only / stale local file only |

## Gap

- One `?` on the Cursor section header only.
- `n/a` when remaining is missing; confirm 0 never collapses to `n/a`.
- Digest is local `bob-peers/digest.json` only — must HTTP GET `https://irc.ntsa.uk/bob/v1/report` (`Get-BobDigestUrl` / `reportUrl`; FR #354). Do not use `bob.ntsa.uk/bob/v1/digest`.

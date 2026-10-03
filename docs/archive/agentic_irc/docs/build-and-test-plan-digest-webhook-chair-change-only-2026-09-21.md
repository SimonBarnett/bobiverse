<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-digest-webhook-chair-change-only-2026-09-21.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: change-only webhook + chair

**FR:** `docs/feature-request-digest-webhook-chair-change-only-2026-09-21.md`

## Phase 1 — Protocol + callback

- Document POST body schema (delta fields, no heartbeat-only).
- `bobcallback` / `apply_callback`: no-op path, metrics log line.
- Remove or gate channel `BOB DIGEST` / fleet English from briefer path when chair enabled.

## Phase 2 — Chair seat

- `bobiverse.json`: `chairNick` `Jeeves`. Chair `--home` is `~\.agentic-irc-jeeves`. Do not reuse the bob-ionos home.
- `irc_agent.py --chair` nick `Jeeves`. `BOB_DIGEST_HOME` is `~\.agentic-irc-bobiverse` so `chair-outbox.txt` drains.
- `scripts/Install-BobChair.ps1` sets both. BobIrcd NSSM auto-start lives in agentic_build. Watch does not start the chair.

## Phase 3 — Producer delta POST (with build #124)

- `Write-BobIrcStatus`: hash canonical peer blob; POST only on change.
- Test-Pack fixture: two ticks same data → zero POST.

## Phase 4 — Tests + skills

- `test_bobreport` / `test_bobcallback`: duplicate POST, whisper-only digest.
- Update `bob-irc` skill; harvest to agentic_build.

## MRB evidence

- pytest subset; redacted log: no `PRIVMSG #bobiverse :BOB DIGEST` in 5 min idle.
- One deliberate fuel change → one POST (Fake HTTP or integration test).

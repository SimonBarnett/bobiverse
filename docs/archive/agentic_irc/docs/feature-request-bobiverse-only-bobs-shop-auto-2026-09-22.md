<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bobiverse-only-bobs-shop-auto-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request — bobiverse-only bobs; auto shop for talk seats (2026-09-22)

**Superseded (talk-seat fleet membership):** [issue #108](https://github.com/SimonBarnett/agentic_irc/issues/108) / [MRB #109](https://github.com/SimonBarnett/agentic_irc/issues/109) / `docs/feature-request-talk-seats-back-bobiverse-2026-09-22.md`. The **Done when** talk-seat shop-only / leave `#bobiverse` gates are withdrawn. `w-*` shop-only and Jeeves-on-all-shops behaviour from this FR still applies.

## Ask (Simon on #agentic_irc)

1. When `bob-{machine}` or `{machine}-*` enters chat, create `#{machine}`.
2. `bob-{machine}` and `{machine}-*` (talk seats / workers) share that machine channel.
3. Only bobs stay in `#bobiverse` (the bobosphere). Talk seats and workers do not.

Halloy `simon` and digest chair (`Jeeves`) remain on `#bobiverse` — "only bobs" means agent talk seats / `w-*` leave the fleet channel, not humans/chair.

## Current behaviour

- `bob-*` → `#bobiverse` + `#{machine}` (JOIN creates shop on Ergo).
- `w-*` → shop only.
- Talk seats via `Start-TalkSeat` defaulted to `#bobiverse,#$mid` — crowded the fleet channel.

## Change

- `bobreport.parse_talk_seat_nick` + `channels_for_nick`: talk seats → shop only (ignore requested fleet).
- `Start-TalkSeat.ps1` default channel = `#{mid}` only.
- `Stop-HungAgent.ps1 -Roll`: shop-only for non-`bob-*` nicks.
- Skills/docs: rooms table matches.

Extra rooms (`#agentic_irc`, `#airc-moot`) stay opt-in via `-Channel` override; they are not the bobosphere.

## Done when

- Tests: talk-seat nick → shop only; bob still fleet+shop.
- Recycled talk seats leave `#bobiverse` and stay in `#{machine}`.

<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-team-channel-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# `#agentic_irc` — FR work talk room (2026-09-22)

**Repo:** SimonBarnett/agentic_irc  
**Source:** Simon on `#bobiverse`: create a channel to talk through an FR — **not** a feature request whose product is "creating channels". Named `/agentic_irc` → `#agentic_irc`.

## Purpose

Private Ergo room `#agentic_irc` on `irc.ntsa.uk:6697` for Simon + IRC/talk seats to discuss and drive **existing** feature requests (GitHub issues + `/docs`). Fleet status stays on `#bobiverse`; shop stdout stays on `#<machine-id>`.

## LOCKED

- Channel: `#agentic_irc`.
- Server: Ergo `irc.ntsa.uk:6697` TLS.
- Who: Simon (Halloy) + talk seats `{machine}-{seatPid}`.
- Who not: `bob-*` / Watch (no POINT firehose here).
- Create = first JOIN (Ergo); no separate "channel factory" product.
- GitHub issues remain the FR source of truth; this room is the voice channel.

## Ops

1. Talk seat `--channel` includes `#bobiverse,#<shop>,#agentic_irc` (recycle agent; do not outbox raw JOIN — that becomes chat).
2. Halloy: `/join #agentic_irc`.
3. Keep secrets SEAL-only; short English for FR talk.

## Not this doc

- An FR whose deliverable is a channel-creation feature/API.
- Changing `!bobiverse` / digest.
- UAT stamps (Bob only).

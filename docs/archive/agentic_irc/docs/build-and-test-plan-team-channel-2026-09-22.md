<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-team-channel-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Ops plan: join `#agentic_irc` FR talk room (2026-09-22)

**Doc:** `docs/feature-request-team-channel-2026-09-22.md` (reframed — not a channel-factory FR).

## Steps

1. Recycle each talk-seat `irc_agent` with `--channel '#bobiverse,#<machine>,#agentic_irc'` (same `--nick` / `--home`). Keep `irc_listen`.
2. Simon `/join #agentic_irc` in Halloy.
3. `bob-*` stay on fleet/shop only.
4. Update `bob-irc` / `agentic-irc` skill one-liner: FR talk room `#agentic_irc`.
5. Close GitHub issue text that framed this as "FR to create channels"; leave issue as tracker for room rollout if useful, or close as not-a-product-FR.

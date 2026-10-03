<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/retire-ear-bored-offer-fr233.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #233: Retire bob-* ear `!bored` OFFER path

## Why

gh-Jeeves #106 (CAST IRON): **Jeeves** assigns the next job when a worker
sends `!bored` in `#{machine}`. An ear that also OFFERs races Jeeves.

## Change

`irc_agent` bob-* ears (`fleet_bob`, not `--chair`) treat `!bored` as a
**no-op**: log `git-claim bored ear-noop` and do not call `offer_top` or
write ASSIGN. ACK/DONE and other shop duties remain.

## Tests

`tests/test_git_claim.py::test_bob_ear_bored_is_noop_jeeves_assigns`

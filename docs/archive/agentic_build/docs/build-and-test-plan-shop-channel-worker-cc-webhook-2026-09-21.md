<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-shop-channel-worker-cc-webhook-2026-09-21.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan — shop worker attach + reportUrl

**Repo:** SimonBarnett/agentic_build
**Spec:** docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md
**Issue:** #124
**Sister:** agentic_irc #46

## P0
Read sister FR. Do not invent a fifth machine id.

## P1
`bobiverse.json` `reportUrl`. Skills: `bob-shop-worker`, `bob-irc`,
MRB/build kickoff paragraphs.

## P2
Watch: JOIN shop; no POINT/`!report` outbox; POST on local death.

## P3
Ionos write-only listener if dispatched; otherwise leave as documented
hole for a later ticket.

## P4
PR. Hostile MRB #124. Bob UAT.

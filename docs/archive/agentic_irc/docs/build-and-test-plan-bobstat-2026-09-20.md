<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-bobstat-2026-09-20.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan: BOB v1 POINT fleet status

**FR:** `docs/feature-request-bobstat-2026-09-20.md`  
**MRB board:** https://github.com/SimonBarnett/agentic_irc/issues/5  

## Steps

1. Read `scripts/bobstat.py` wire format, `MAX_POINT`, `ID_RE`, job token rules.
2. Confirm `irc_agent.py` ingests POINT trailing text and logs `INFO bobstat id=…`.
3. Run `pytest tests/test_bobstat.py` (offline).
4. Manual (Ergo only, not CI): chair POINT a sample line on `#bobiverse`; verify `bob-peers/<id>.json` updates on a listening `irc_agent` home.
5. README: link FR, document id charset and truncation; state cleartext threat model.
6. Commit/push; open PR; Bob chairs MRB — **do not** stamp ready for human UAT until PASS.

## Success

FR MUST/MUST NOT reflected in docs; pytest green; optional live POINT row noted in PR comment. No secrets in tree.

## Out of scope for CI

Libera, live `#bobiverse`, and two-nick registration (see FR #3 / `docs/multi-agent-one-host.md`).

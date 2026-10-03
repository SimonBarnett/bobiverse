<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-irc-multi-agent-registration-2026-09-20.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan: multi-agent irc_agent registration (no 001)

**FR:** `docs/feature-request-irc-multi-agent-registration-2026-09-20.md`

## Steps

1. Read `scripts/irc_agent.py` CAP/NICK/USER/001/JOIN timeout path; compare with working `cm-slab` session logs on IONOS.
2. Reproduce or document: second nick same public IP → no 001.
3. Improve TimeoutError INFO (NO 001 vs NO JOIN); add reconnect backoff.
4. Document multi-agent-on-one-box Libera limits / workarounds in `docs/multi-agent-one-host.md` (dated IONOS row + workarounds).
5. Check Windows stdout redirect / Start-Process deadlock notes.
6. pytest + manual notes; commit/push. Merc UAT+MRB; Tweet cm-tweet join re-test only.

## Success

FR acceptance green; Tweet can join as cm-tweet alongside cm-slab or has a documented path.

## Ownership update (2026-09-20)

Tweet is **reporter only** (not agentic_irc UAT owner). **Slab** owns UAT + hostile MRB after the build lands. Tweet will re-test `cm-tweet` join on IONOS when a candidate tip is ready.

Ownership: Merc UAT+MRB; Tweet join re-test only.

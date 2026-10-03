<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-bobstat-point-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan: park BOB v1 POINT / bobstat FR

**FR:** `docs/feature-request-bobstat-point-2026-09-21.md`  
**MRB home:** https://github.com/SimonBarnett/agentic_irc/issues/8  
**Closes FAIL item:** MRB #5 blocker 1 (park FR + plan; code already on `main`)

## Scope (this dispatch)

Park documentation only. **Do not** add new BOB v1 wire fields or quiet-talk behaviour (#6).

## Steps

1. Read `docs/feature-request-bobstat-point-2026-09-21.md` and issue #8 LOCKED list.
2. Confirm `scripts/bobstat.py`, `scripts/irc_agent.py` POINT ingest, and `tests/test_bobstat.py` match the FR wire table (no code change unless drift).
3. Run offline gate: `pytest -q tests/test_bobstat.py` (full `pytest -q` if touching shared imports).
4. README: link FR; document lowercase `id=` rule and 350-char truncation behaviour.
5. Open PR; comment on MRB #5 that blocker 1 is addressed. Bob chairs hostile MRB on #8.

## Success

- FR + this plan on the branch; PR open (not merged by worker).
- MRB #5 required fix #1 satisfied for the bobstat track.
- No `password=` / `XAI_API_KEY=` in git; no ready-for-human-UAT stamp for bobstat.

## Evidence expected in PR

| Gate | Method |
|---|---|
| Parse/format roundtrip | `tests/test_bobstat.py` |
| MOOT POINT transcript | `test_point_on_free_moot_writes_peer` |
| CI | `.github/workflows/test.yml` offline pytest |
| Live Ergo POINT | Manual / fleet; **not** CI |

## Non-goals

- Libera two-nick 001 (FR #3).
- Live `#bobiverse` POINT smoke in pytest.
- Human UAT stamp or MRB PDF.

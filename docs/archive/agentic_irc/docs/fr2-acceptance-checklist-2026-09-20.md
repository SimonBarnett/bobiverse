<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/fr2-acceptance-checklist-2026-09-20.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #2 acceptance checklist (Mode 3 DUMB exec ergonomics)

**FR:** `docs/feature-request-mode3-dumb-exec-ergonomics-2026-09-19.md`  
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/2  
**Park commit:** `c51d2f6` (docs only — FR + build-and-test plan)  

Status for issue #5 required fix #3 — **not** a PASS; tracks what landed vs open.

| # | Acceptance item | Status | Evidence |
|---|-----------------|--------|----------|
| 1 | `docs/mode3-dumb-ops.md` (bins, META_CHARS, `//`, 60s cap, put+spawn+poll) | **Open** | Plan step 2; file not in tree at `c51d2f6` |
| 2 | Operator errors distinguish meta vs bin vs jail | **Open** | `dumb_agent.py` still uses generic policy failures; no `empty_argv` split |
| 3 | (Stretch) `download` / `spawn` helpers | **Open** | Not implemented |
| 4 | Tests + Slab UAT on flamingo thin | **Open** | pytest covers protocol; no ergonomics doc UAT row |

**Next build:** ship `mode3-dumb-ops.md`, error-code split in Python + thin/.NET parity, then Slab hostile MRB on issue #2. Do not close issue #2 from docs-only parking.

<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/wp-backlog-full-irc-2026-09-19.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Work package backlog - finish agentic_irc (2026-09-19)

Owner: Bob orchestrates; build agents on **ionos** implement. Prefer model build0.1 when available.

## Already closed (do not re-open without evidence)

| WP | Status |
|---|---|
| Mode 1 agent-to-agent SEAL+FILE | Ready for human UAT (mrb-mode1) |
| Mode 2 moot + FILE | Ready for human UAT (mrb-mode2-retest) |
| Python moot/file/dumb phases 0-4 | Ready for human UAT (mrb v2); gap blockers 1-4 closed |
| Mode 3 P0-P3 thin client + Release | PASS-with-nits (mrb-mode3); A5 open |

## Open WPs (priority order)

### WP-M3-A5 - Mode 3 live IONOS smoke (UAT blocker)
**Status (2026-09-19):** **CLOSED** at `4abdce5` / mrb-mode3-a5-retest. Mode 3 ready for human UAT on Win8+ Schannel only.
**Goal:** Chair `cm-bob` OPEN moot; run release `airc-moot-thin.exe` (or local build); operators allowlist; sealed `exec hostname`; stdout to chair; commit log excerpt under `docs/mode3-live-smoke-2026-09-19.md`.  
**Done when:** Bob can re-MRB Mode 3 toward ready for human UAT (Win8+ only).  
**Do not:** claim Win95; put keys in git; open Libera from CI.

### WP-P5 - .NET 4.5 `airc-dumb.exe` protocol clone
**Status (2026-09-19):** engineering **PASS-with-nits** at `2751f54` (mrb-wp-p5-dotnet). Live Server 2012 Libera smoke still open for UAT.
**Goal:** Replace stub in `src/dumb_dotnet/` with behaviour-compatible clone of `scripts/dumb_agent.py` (TcpClient+SslStream TLS 1.2, CAPA, PSK DUMB jobs, jail, ping/sysinfo/exec/get/put). MSBuild net45; no runtime NuGet crypto if avoidable. Offline tests via `DOTNET_DUMB_EXE` where possible. Update README + skill honesty.  
**Status:** implemented in tree (pending Bob MRB). **Not** ready for human UAT.  
**Do not:** break Python dumb; Mode 3 is separate.

### WP-YIELD - `YIELD *` returns floor to chair
**Goal:** Align state machine with Table 3 prose (return floor to chair, not `floor=None` only). Offline test.  
**Priority:** after M3-A5 / with small fix pass.

### WP-FLOOR-IDLE - `FLOOR_IDLE_S`
**Goal:** Optional chair hint per PDF (skill was only). Implement or explicitly waive in gap doc.  
**Priority:** low / optional v1.

### WP-AGPK-DUMB - AGPK-mode dumb jobs (optional)
**Goal:** SEAL-v2 job unwrap on connector if PDF still requires; PSK remains default.  
**Priority:** after P5 unless Simon prioritizes.

### WP-GAP-DOC - Refresh gap + feature-request status
**Goal:** One honest status table: Mode1/2/3 UAT, P5, waived items. Remove contradictory "do not claim UAT" vs "ready for human UAT" lines where outdated.

### WP-WIN95 (optional / new spike)
**Goal:** Only if Simon still wants true 9x: OpenWatcom + static TLS or relay. Separate FR. Not required to close current Mode 3 UAT.

### Human-only
- `tests/MANUAL.md` full Libera session checklist (operator).

## Dispatch plan this push

1. Queue **WP-M3-A5** on ionos cwd `C:\ai\agentic_irc`.
2. Queue **WP-P5** on ionos (may run after or parallel if workers free).
3. Follow with WP-YIELD + WP-GAP-DOC in a cleanup ticket after P5 or bundled if small.
<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mrb-mode2-fix-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB — Mode 2 fix pass (2026-09-19)

**Job:** `b7e626f5` on ionos  
**Range:** `9c9dc20..d4330db`  
**Prior:** [mrb-mode2-2026-09-19.md](./mrb-mode2-2026-09-19.md) PASS-with-nits

## Verdict

**PASS** for the four required mode-2 blockers. Ready for a live re-probe of moot JOIN roster on chair + FILE first-offer when Simon wants. Not a claim of full Libera manual matrix / .NET.

## Close-out

| # | Required | Status |
|---|---|---|
| 1 | Chair roster persists JOINA | **Closed** — load/apply/persist `moot/<id>.json` (own PRIVMSG not echoed) |
| 2 | Chair transcript OPEN/JOIN/FLOOR/SAY/YIELD/CLOSE | **Closed** |
| 3 | FILE first-offer flake | **Closed** — complete newline drain + atomic OFFER+SEAL append |
| 4 | Offline tests | **Closed** — 84 passed, 2 skipped |

## Evidence

`pytest -q` on IONOS post-pull: **84 passed, 2 skipped**.

**Bob:** mode-2 fix PASS. Optional next: live 3-nick moot re-run to confirm chair roster on disk under real Libera non-echo.
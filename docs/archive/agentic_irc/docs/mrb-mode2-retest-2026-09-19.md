<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mrb-mode2-retest-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB — Mode 2 live retest (2026-09-19)

**Tip:** `7dd8348`  
**Moot:** `bc79d0c45f545c34` on `#cm-bob-oscar` (IONOS)  
**Nicks:** cm-bob (chair), cm-oscar, cm-spider  
**Offline:** 88 passed, 2 skipped

## Verdict

**PASS — ready for human UAT** of mode-2 moot + SEAL + FILE on IONOS.

Prior PASS-with-nits (`mrb-mode2-2026-09-19.md`) blockers are closed under live Libera non-echo.

## Live evidence

| Check | Result |
|---|---|
| Chair roster after JOIN | `cm-bob,cm-spider,cm-oscar` |
| Chair roster at CLOSE | same; `state=closed` |
| Chair transcript | OPEN, JOIN×2, FLOOR×2, SAY×2, YIELD×2, CLOSE |
| SEAL bob→oscar / bob→spider | inbox bytes landed |
| FILE tier S first offer | `INFO file DONE id=3ca2fd5816d98577 ok` (and prior `52467582… ok`) |

## Remaining non-goals

.NET Phase 5; AWS Libera without SASL; full manual moot matrix beyond this probe.

**Bob:** mode-2 PASS ready for human UAT.
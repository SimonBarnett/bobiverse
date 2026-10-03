<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-jeeves-windows-service-330.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #330: Jeeves as its own Windows service

**Issue:** https://github.com/SimonBarnett/agentic_build/issues/330  
**Status:** Completed in **SimonBarnett/gh-Jeeves** (cutover). This note parks the agentic_build pointer.

## Success metric (Simon)

Token-less path: GitHub event → announce + queue/supersede → worker `!bored` → assign → ACK → busy on webhook → DONE → done/idle/supersede. Scripts only; worker AI is the only LLM. Proven by gh-Jeeves G1 / FR #1.

## Where it lives

| Piece | Repo |
|---|---|
| Service installer | `gh-Jeeves/tools/Install-BobJeeves.ps1` |
| Start helper | `gh-Jeeves/tools/Start-BobJeeves.ps1` |
| Token-less gate | `gh-Jeeves/tests/g1_token_less_e2e`, skills `jeeves-token-less-gate` |
| Related closed FRs | gh-Jeeves #1, #7, #17, #39, #48 |

## agentic_build leftovers

`tools/Install-BobJeeves.ps1` here remains the **legacy** NSSM + `agentic_irc` chair. When a sibling `gh-Jeeves` tree exists, it refuses to install unless `-AllowLegacyAgenticIrc`. Skill `bob-jeeves-chair` documents the cutover.

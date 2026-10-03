<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-systray-restore-agent-icons-2026-09-23.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: restore systray Cursor/Grok icons

## Phase 1
1. Fix `Resolve-BobTrayAgentExe` to return `$null` when no candidate exists.
2. Add `Get-BobTrayAgentBrandImage` (or extend `Get-BobTrayAgentImage`) that: prefers desktop app exe for icon extract; falls back to a drawn badge (C / G) when extract fails or image is empty; greyscale only when not installed, without making the icon invisible.
3. Wire TipForm section headers + Agents menu through that helper.

## Phase 2
Test-Pack: Resolve returns null when missing; Grok Bot.exe preferred for icon; badge fallback exists; section header code still calls Get-BobTrayAgentImage.

## Done
A1–A6; PR; MRB PASS-nits.

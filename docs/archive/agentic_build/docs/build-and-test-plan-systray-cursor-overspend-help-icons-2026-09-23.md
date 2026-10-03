<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-systray-cursor-overspend-help-icons-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: systray Cursor overspend / help / icons (#266)

FR: `docs/feature-request-systray-cursor-overspend-help-icons-2026-09-23.md`.

1. `tools/Watch-BobTray.ps1` TipForm / hover card only.
   - Separate labelled Cursor vs Grok account sections.
   - Cursor overspend line from existing box-usage / hover payload: `overspend £N.NN` red when > 0; omit zero.
   - Section icons: `Icon.ExtractAssociatedIcon` on the same Cursor/Grok exes as the Agents menu.
   - Help `?` with ToolTip covering Grok chat, high-cost, low-cost; low-cost = Cursor build fuel gate.
2. Reuse `Get-BobTrayAgentImage` (or equivalent) — do not invent a second icon path.
3. BT0l / Test-Pack: strings for overspend format, help tooltip, section labels, ExtractAssociatedIcon.
4. Open PR. Do not push `main`. Recycle Watch-BobTray only to smoke. No UAT.

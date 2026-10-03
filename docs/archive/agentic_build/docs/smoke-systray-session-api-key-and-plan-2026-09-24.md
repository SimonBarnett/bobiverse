<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/smoke-systray-session-api-key-and-plan-2026-09-24.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Smoke: TipForm session API key + Plan seats (2026-09-24)

## Session API key (empty fuel)
1. Recycle tray only if needed (kill Watch-BobTray, start `_Watch-BobTray-marchhare.ps1`) so it loads this branch.
2. Open TipForm (left-click Bob Fleet) or right-click **Agents**.
3. With this machine Grok weekly / Cursor auto remaining **> 0**: Start Grok/Cursor — no dialog (unchanged).
4. With remaining **0%**: Start Grok → password dialog for `XAI_API_KEY`; Cancel aborts; OK launches child with process-scoped env only (no User/Machine env, no auth.json write).
5. Cursor remaining 0% → same for `CURSOR_API_KEY`.

## Plan -> Grok / Cursor
1. Right-click tray → **Plan** (top-level, next to **Agents**) → **Grok** or **Cursor**.
2. First run syncs https://github.com/SimonBarnett/skills-visionary (clone under D:\ai / C:\ai / C:\src) and copies visionary skills into `~/.grok/skills`.
3. Agent opens in plan mode (Grok `--permission-mode plan`, Cursor `--plan`) with cwd/workspace = skills-visionary clone.
4. No Watch-AgentHealth, no IRC / Watch-Bobiverse, no agentic_build work repo.
5. Empty fuel reuses the same session API key dialogs.

## Automated
`tools/Test-Pack.ps1` BT0l asserts source contracts (fuel dialog helpers, Plan menu, Install-VisionarySkills, no User/Machine SetEnvironmentVariable).

<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-systray-cursor-overspend-help-icons-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: systray Cursor usage, overspend, help, and account icons

https://github.com/SimonBarnett/agentic_build/issues/266

Parked from cursor[bot] request. Product: `tools/Watch-BobTray.ps1` TipForm card.

## LOCKED

1. Show Cursor on-demand overspend whenever usage exceeds the included allowance. Format `overspend £N.NN` in red. Do not show a zero-value overspend line.
2. Put all Cursor figures in their own clearly labelled section. Use the same Cursor icon the Agents launcher already uses (`Icon.ExtractAssociatedIcon` on the Cursor exe).
3. Put Grok account figures in a separate section. Use the Grok exe icon (Agents menu parity).
4. Add a help (`?`) control. Hover text explains the three Cursor usage brackets (Grok chat, high-cost models, low-cost models) and identifies the low-cost bracket as the Cursor build fuel gate.
5. Existing machine tiles, usage bars, jobs, alerts, and click-only card behaviour stay intact.
6. Recycle Watch-BobTray only. Do not add a second NotifyIcon. Harvest as PR, not `main`. No UAT. No secrets.

## UNKNOWN

Exact GBP field name already on the usage packet (`account_overspend` vs derived). Use the live box-usage / hover payload; do not invent a second billing API.

## Acceptance

| ID | Gate |
|---|---|
| A1 | Cursor usage and Grok accounts are visually separate labelled sections. |
| A2 | Positive Cursor on-demand overspend shows `overspend £N.NN` in red; zero omitted. |
| A3 | Cursor and Grok section icons reuse Agents-menu executable icons. |
| A4 | Help `?` hover explains all three Cursor brackets; low-cost = Cursor build fuel gate. |
| A5 | Machine tiles, bars, jobs, alerts, click-only card unchanged. |

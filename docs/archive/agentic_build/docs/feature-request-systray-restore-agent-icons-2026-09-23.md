<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-systray-restore-agent-icons-2026-09-23.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: restore Cursor / xAI (Grok) icons on systray tip + Agents menu

## Summary
Simon (agentic_irc #182, 2026-09-23): the xAI / Cursor icons disappeared from the systray. Add them back.

## Gap vs current tree
`Get-BobTrayAgentImage` extracts from `$Agent.exe`. `Resolve-BobTrayAgentExe` can return a **non-existent** first candidate (Cursor) or prefer CLI `grok.exe` over `Grok Bot.exe`. Missing exe → robot fallback + heavy greyscale (`Matrix33=0.60`) which vanishes on the dark TipForm. Blank/near-transparent extracted icons also look "gone".

## Acceptance
| ID | Criterion |
|----|-----------|
| A1 | TipForm section headers always show a distinct Cursor icon and a distinct Grok/xAI icon (not blank, not missing). |
| A2 | Agents submenu entries show the same branded icons. |
| A3 | Missing Cursor.exe still shows a Cursor-branded (or clearly labelled) icon, not an empty PictureBox. |
| A4 | Grok icon prefers `Grok Bot.exe` for ExtractAssociatedIcon when that file exists. |
| A5 | `Resolve-BobTrayAgentExe` does not treat a missing path as "found". |
| A6 | Test-Pack asserts A4–A5 (and that section headers pass non-null icon path / fallback helper). |

## Out of scope
- Separate NotifyIcons per agent in the Windows tray area (still one Bob Fleet icon).
- flamingo remote recycle from DEV1.

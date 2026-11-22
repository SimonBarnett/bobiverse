# BOB-54 Priority menu icon

FR #8694. Agents > Priority uses the existing Priority client icon.

- Asset: `bob/vendor/priority/priority.ico` (same folder as `PriorityAgent.exe` from BOB-50).
- Source bytes: priority-mcp `launcher/priority.ico` (PRI-07). This slice does not draw a new icon.
- Tray log: `priority-icon path=vendor/priority/priority.ico` (Watch-BobTray and bob-tray.exe).
- Start behaviour is unchanged (BOB-50).

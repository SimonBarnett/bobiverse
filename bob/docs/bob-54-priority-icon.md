# BOB-54 Priority menu icon

FR #8694 / FR #9269 (BOB-TRAY-UI-08). Agents > Priority uses the Priority client icon from tray assets.

- Asset: `bob/tray/assets/priority.ico` (install sync lays it at `<install>\assets\priority.ico`, same pattern as plan-gantt).
- Source bytes: priority-mcp `launcher/priority.ico` (PRI-07). This slice does not draw a new icon.
- Tray log: `priority-icon path=.../assets/priority.ico` (Watch-BobTray and bob-tray.exe).
- FR #9269: Priority is a flat click (no Start / Configure MCP submenu); start behaviour remains BOB-50 + BOB-52 fuel gate.

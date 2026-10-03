<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-shortcut-hidden-background-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: shortcut watch clients start hidden

https://github.com/SimonBarnett/AgentMonitor/issues/61

Push `c491e587` on branch `issue-32-tui-launch-ps1` (stale name). PR https://github.com/SimonBarnett/AgentMonitor/pull/60. No UAT.

## LOCKED

1. One-click `.cmd` shortcuts and Desktop `.lnk` targets should start Watch-AgentHealth in the background (`-Windows off`), not a visible console.
2. Main `Watch-AgentHealth.cmd` stays visible by default unless the operator passes `off`.
3. README and `agent-monitor` skill must match: shortcuts hidden; main `.cmd` visible unless `off`.

## Gap vs `e81fea9` (main)

Shortcut launchers still run visible / foreground. README said shortcuts start visible.

## Acceptance

| ID | Gate |
|----|------|
| A1 | `Watch-AgentHealth-*-New.cmd` and `Watch-AgentHealth-*-Resume.cmd` (cursor + grok) start the worker hidden (`WindowStyle Hidden` or equivalent). |
| A2 | Main `Watch-AgentHealth.cmd` without `off` remains visible (`-NoExit` console). |
| A3 | `off` on the main `.cmd` still hides watch console and agent TUI. |
| A4 | `docs/operator-playbook.md`, README, and `agent-monitor` skill text match A1–A3. |
| A5 | No UAT stamp. |

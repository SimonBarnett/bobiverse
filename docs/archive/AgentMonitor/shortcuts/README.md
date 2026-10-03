<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path shortcuts/README.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# shortcuts/

`tools\Publish-DesktopShortcuts.ps1` writes the Watch-AgentHealth `.lnk` files here
and to the Desktop. They are **generated per machine**, because each one holds that machine's clone path
and agent `.exe` icon, so `shortcuts/*.lnk` is gitignored and not tracked.

Regenerate with `tools\Publish-DesktopShortcuts.ps1` (agentic_build `Install-AgentMonitor.ps1` runs it).
After an install the clone's `git status` stays clean.

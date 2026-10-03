<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .github/copilot-instructions.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Copilot on agentic_build

PowerShell 5.1. Run `tools\Test-Pack.ps1` after fleet/tray/IRC changes.

`Watch-Bobiverse.ps1` must not invoke grok.exe. Live `grok.exe` on a machine still appears on the Bob Fleet tray even if Bob did not start it. `Grok Bot.exe` is not a Build agent.

No SMB peer peek. Status is `#bobiverse` MODE2. See `docs/bobiverse.md`.

Do not commit secrets, `password=` or `XAI_API_KEY=` assignments.

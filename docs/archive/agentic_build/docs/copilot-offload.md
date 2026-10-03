<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/copilot-offload.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Offload repo work to GitHub Copilot

Cursor/Grok Bot weekly usage is a different seat from Grok Build (`grok.exe` / xAI). GitHub Copilot cloud agent bills **SimonBarnett Copilot credits**.

## Agent start

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Start-BobCopilot.ps1 -Prompt 'Add tests for Watch-Bobiverse idle heartbeat'
```

Hostile MRB (Bob hands off, does not write the review):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Start-BobMrbHandoff.ps1 -Issue 8 -Repo SimonBarnett/agentic_build
```

Assign an existing issue:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Start-BobCopilot.ps1 -Issue 12
```

`gh auth login` as the GitHub user (not an installation token).

Grok always opens a **git issue** with `@copilot`. Cloud-agent assign needs CCA **on that repo** (org policy **Coming soon** is not enough). Until then the issue is the handoff; Copilot will not start a session.

Paid Copilot + cloud agent: https://github.com/settings/copilot/features and the repo Copilot settings.

## Not for

Bob fleet `Watch-BobJobs` / MSSQL integrated `grok.exe` on a build box.

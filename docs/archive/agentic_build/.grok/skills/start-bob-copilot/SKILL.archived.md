<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/start-bob-copilot/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: start-bob-copilot
description: >
  Start GitHub Copilot cloud agent on a SimonBarnett repo from this Grok
  session. Use when the user says start Copilot, assign Copilot, offload to
  Copilot, GitHub coding agent, or /start-bob-copilot. Bills GitHub Copilot
  credits, not Cursor weekly usage and not grok.exe. Before start, pass the
  digest fuel gate (bob-token-handoff). Copilot is not the default while
  cursor-models remaining is above 0.
---

# Start Bob Copilot

Copilot is an optional fuel (`-AllowCopilot`), including hostile MRB only when the picker chose `copilot`. Bob uses `tools/Start-BobMrbHandoff.ps1`. Default MRB/PR fuel is cursor-models then grok-build (`bob-token-handoff`), not this script.

## Digest fuel gate (before start)

Follow `bob-token-handoff` first. GET `https://irc.ntsa.uk/bob/v1/report` and read `pcent.cursor-models`. Do not invent the percent.

Start Copilot only when fuel is `copilot`: the operator passed `-AllowCopilot` / `-Fuel copilot`, and included `cursor-models` is already 0 (or the picker explicitly chose copilot). While `cursor-models` remaining is above 0, do not offload here. Never Other Models. PR stays the low tier; MRB stays medium (`grok-4.6`) on cursor-models or grok-build. UAT stays with Bob.

Reached via `Select-BobGitWorker` when fuel is `copilot` (same picker as
`start-bob-cursor`). Grok **hands off** by opening a GitHub issue that
`@copilot`s Copilot, then tries the cloud-agent task API. If GitHub returns
`CCA not enabled`, the issue is still the handoff -- do not implement that
work in Grok Bot or extra grok.exe.

## Command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Start-BobCopilot.ps1 -Prompt '...' -Repo SimonBarnett/agentic_build -BaseRef main
# or -Issue <n> to assign copilot-swe-agent[bot]
```

Requires `gh.exe` logged in as SimonBarnett (user token). Installation tokens fail. If Copilot is missing from Assignees, enable cloud agent at github.com/settings/copilot/features.

See `docs/copilot-offload.md`.

While a Copilot git packet is in `fleet\running`, `Write-BobIrcStatus` on
that machine owns the digest row. When the handoff finishes or is stopped,
the next publish must **clear** `jobs` and zero `running`/`queued` on
`reportUrl` (same as cursor-models).

## When Grok starts a build agent

`Start-BobWorker` copies this repo's `.grok/skills` (https://github.com/SimonBarnett/agentic_build) into `~/.grok/skills` and adds that path on grok.exe `--rules`. Fleet prompt also names `start-bob-copilot`. The build `grok.exe` should call `Start-BobCopilot.ps1` for GitHub repo work instead of Grok Bot.

Bob fleet jobs that need Windows logon (MSSQL) stay on `grok.exe`.

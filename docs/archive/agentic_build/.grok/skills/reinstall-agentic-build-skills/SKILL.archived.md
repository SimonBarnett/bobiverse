<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/reinstall-agentic-build-skills/SKILL.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: reinstall-agentic-build-skills
description: >
  Sync SimonBarnett/agentic_build project skills into ~/.grok/skills after
  git pull, skill harvest, or a broken skills tree. Use when the user says
  reinstall skills, refresh bob skills, sync agentic_build skills, copy
  skills to ~/.grok, or /reinstall-agentic-build-skills.
---

# Reinstall agentic_build skills

Not harvest (`harvest-agent-skills`). Not dispatch (`Start-BobBuild`). Not a second NotifyIcon.

## Command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Reinstall-AgentSkills.ps1
# optional: -Pull   (ff-only origin/main if the tree is clean)
# optional: -RecycleTray   (kill every Watch-BobTray, start exactly one)
```

Repo resolve order: `-RepoRoot`, then `D:\ai\agentic_build`, `C:\ai\agentic_build`, `C:\src\agentic_build`. Clone `https://github.com/SimonBarnett/agentic_build` if missing.

Copy path is `Copy-BobProjectSkills`: every `.grok/skills/*/SKILL.md` -> `~\.grok\skills\<name>\SKILL.md` (same as `Install-BobFleet`).

Prints copied skill names + HEAD SHA. Never commits. Never starts product builds.

## Tray recycle (`-RecycleTray`)

Kill `Watch-BobTray.ps1` processes, start **one** hidden STA instance. Do not `Stop-ScheduledTask BobFleet-*`. Do not kill `Watch-BobJobs` or in-flight `grok.exe`. See issue #3 / `bob-fleet-tray` (one TipForm, no second NotifyIcon).

Safe on ionos / flamingo / marchhare / ce-priority-dev1.

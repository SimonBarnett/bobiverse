# Watch-AgentHealth (fleet snapshot)

Canonical home: https://github.com/SimonBarnett/bobiverse (`bob/agentwatcher`).
(Former AgentMonitor product is archived into bobiverse — FR #836.)

`Install-BobFleet` copies this folder to `%USERPROFILE%\Desktop\Watch-AgentHealth`.
Create a build-worker seat with `tools/Start-BobWatchWorker.ps1` or the hidden
shortcuts. Skill: `watch-agent-health`.

CI (FR #9765): `.github/workflows/build-bob-agentwatcher.yml` sparse-checkouts
`bob/agentwatcher` plus `bob/scripts/Build-BobWatcher.ps1` and uploads artifact
`bob-agentwatcher` (`Watch-AgentHealth.exe`, sha256, `MANIFEST.json`, `provenance.txt`).

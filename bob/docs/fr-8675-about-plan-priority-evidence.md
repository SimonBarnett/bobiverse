# FR #8675 / BOB-10 evidence: About Plan + Priority versions

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8675
**Slice:** About shows Plan and Priority build versions (Success S1)

## S1

About (compiled `bob-about.exe` / tray About, and TipForm fallback) shows non-empty `plan <version>` and `priority <version>` under the bob line.

## How measured

1. `Write-BobiversePlanIdentity` stamps `plan\VERSION` + `plan\BUILD.json` from Pack / Install-Bob / Sync.
2. `Common.PlanVersion` / `Common.PriorityVersion` (and PowerShell twins) implement the fallbacks `(via bob)` / `not installed`.
3. Priority folders default: `priority-agent`, `priority-mcp` under `BOB_AI_ROOT` / AI roots.
4. `--versions-out` headless seam; `--text-out` unchanged.
5. Tests: `bob/tests/test_fr8675_about_plan_priority.py`.

## Fail-when

Missing Plan/Priority fields, empty strings, or `--text-out` gaining a Plan version header.

## Test run (fr-8675 worktree)

```
python -m pytest -q bob/tests/test_fr8675_about_plan_priority.py
# 3 passed
```

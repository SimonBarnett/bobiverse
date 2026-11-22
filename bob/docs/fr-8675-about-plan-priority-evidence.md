# FR #8675 / BOB-10 evidence

About shows non-empty Plan and Priority build versions.

- `Common.SliceVersion` reads `plan/VERSION` or `priority/VERSION`, else `BOBIVERSE_PLAN_VERSION` / `BOBIVERSE_PRIORITY_VERSION`, else the bob version.
- `AboutForm` label `agentBuildVersions` and headless `--text-out` both print those strings.
- The PowerShell About fallback uses `Get-BobTraySliceVersion`.

`python -m pytest -q bob/tests/test_fr8675_about_plan_priority.py`

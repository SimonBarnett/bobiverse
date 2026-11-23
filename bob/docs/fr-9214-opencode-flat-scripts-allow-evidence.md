# FR #9214 evidence

OpenCode `opencode_fleet_script_roots` now includes flat `<install>\scripts` alongside `bob\scripts` and `common\scripts`. CAST IRON prompts use `resolve_bobiverse_intake_script` (prefer `common\scripts` when present). Corrective after install-scripts reject names the allowed intake path.

## Tests
`python -m pytest -q bob/tests/test_fr9214_opencode_flat_scripts_allow.py bob/tests/test_fr8064_opencode_fleet_script_read.py bob/tests/test_fr8247_opencode_temp_external_dir.py` -> 18 passed
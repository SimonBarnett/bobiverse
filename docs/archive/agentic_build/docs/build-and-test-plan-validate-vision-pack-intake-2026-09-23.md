<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-validate-vision-pack-intake-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build/test plan: validate-vision-pack intake (#275)

1. Edit `.grok/skills/visionary/SKILL.md`: add the validator refuse line
   from skills-visionary (`python tools/validate-vision-pack.py ...`).
2. Edit `.grok/skills/bob-spec-intake/SKILL.md`: New product step 0 and
   FR step 0 run that command (local `tools/` else sister clone
   `C:\ai\skills-visionary`, `D:\ai\...`, `C:\src\...`) and refuse
   park/dispatch on non-zero.
3. BT0: `bob-spec-intake` must match `validate-vision-pack`.
4. Note `docs/skill-harvest-log.md`.
5. `tools\Test-Pack.ps1`. Open PR. Do not push `main`. No UAT.

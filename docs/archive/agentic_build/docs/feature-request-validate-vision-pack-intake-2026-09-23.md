<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-validate-vision-pack-intake-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: bob-spec-intake must run validate-vision-pack

https://github.com/SimonBarnett/agentic_build/issues/275

CAST IRON harvest of skills-visionary #6 / PR #7 (`2c98dfd`).
That repo owns the CLI/CI. This repo owns the intake call site.

## Target repo

`SimonBarnett/agentic_build`. Existing. Do not `gh repo create`.

## Shape

Reuse current: **service** (fleet playbook). No new UI. No new mocks.

LOCKED

## Gap vs current tree (`15d0d2c`)

- `.grok/skills/visionary/SKILL.md` — refuse gate is prose only.
- `.grok/skills/bob-spec-intake/SKILL.md` — visionary first, no validator command.
- No `validate-vision-pack` mention. A copied-unfilled template can still park.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Intake names the command | `python tools/validate-vision-pack.py <vision.md> [--mocks-dir <dir>]` in `bob-spec-intake` + `visionary` | skill text | intake still prose-only |
| S2 | Sister-or-local path | product `tools/validate-vision-pack.py` or skills-visionary clone (`C:\ai`, `D:\ai`, `C:\src`) | skill text | only one hardcoded box path |
| S3 | Refuse on non-zero | park/dispatch blocked when validator exits non-zero | skill text | exit 1 still parks |
| S4 | FR packs too | same command on FR markdown when that is the pack | skill text | new-product only |

LOCKED

## Acceptance

- [ ] `visionary` refuse gate includes the validator command (same line as skills-visionary).
- [ ] `bob-spec-intake` New product + FR steps run it before park/dispatch.
- [ ] BT0 asserts `bob-spec-intake` mentions `validate-vision-pack`.
- [ ] Harvest log note. PR, not `main`. No UAT. No secrets.

# FR #9217: pytest-ascii-bom required on main

## What
Ruleset `required-ci-3948` (id 24874680) on the default branch now requires both:

- `conflict-markers`
- `pytest-ascii-bom`

## Why
PR #9182 merged while `pytest-ascii-bom` was pending/red because only `conflict-markers` was required. Main went red until FIX on #9189. See #9191.

## Evidence
- PUT `repos/SimonBarnett/bobiverse/rulesets/24874680` added context `pytest-ascii-bom` with `integration_id` 15368 (GitHub Actions).
- Confirm: `GET /repos/SimonBarnett/bobiverse/rules/branches/main` lists both contexts.
- Workflow job name must stay exactly `pytest-ascii-bom` (`.github/workflows/pytest-ascii-bom.yml`).

## Ops
Repository admins: do not drop `pytest-ascii-bom` from the ruleset without a replacement gate. Bypass actors unchanged (RepositoryRole admin always).
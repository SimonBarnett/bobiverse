---
name: bobiverse-jeeves-agent-build
description: >
  How a Jeeves agent gets a trustworthy build: GitHub Actions build-jeeves /
  build-bob-worker / build-bob-ear / build-airc / *-msi runs, the deterministic
  !build catalog (FR #8490, UX follow-up #8770), source SHA and artifact hash
  provenance, never from red main, and release rules. Use before any install,
  for "build Jeeves", !build, release, MANIFEST.json, or /bobiverse-jeeves-agent-build.
depends_on:
  - bobiverse-jeeves-agent-monitor
  - bobiverse-build
---

# bobiverse-jeeves-agent-build

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Distilled from how the Bob Grok Bot drove Jeeves/worker/ear builds and the v2.0.x releases (Nov 2026).
Recipe/announce details live in `bobiverse-build`; post-build health uses `bobiverse-jeeves-agent-monitor`.
Output of this skill is a **build receipt** that `bobiverse-jeeves-agent-install` consumes.

## Rules

- **Never push to main.** Workers write code via FR -> PR -> hostile MRB from a different seat -> merge.
  The agent builds only what is already merged.
- **Never build from red main.** Check the workflow for the component on the exact SHA. If main's
  build/test run is red, the candidate is the newest green SHA that contains the fix, or wait for the fix
  FR; file one FR for the red (de-dup first, anti-omnibus).
- **Docs/lesson-only merges do not need a rebuild** (harvest/lesson PRs that touch no shipped code).
- Builds are deterministic and zero-token (CAST IRON in `bobiverse-build`); never spawn a seat to "build".
- `!build` is ops-only (Si or a `bob-*` ear). Ask once; do not re-ask for the same SHA.

## Two build paths

1. **CI artifact (normal path for a single component hotpatch).** Workflows in `.github/workflows/`:
   `build-jeeves.yml`, `build-bob-worker.yml`, `build-bob-ear.yml`, `build-bob-tray.yml`, `build-bob-plan.yml`,
   `build-airc.yml`, `build-jeeves-webhooks.yml`, and MSIs `build-jeeves-msi.yml`, `build-bob-msi.yml`,
   `build-airc-msi.yml`. They run on push to main for their paths, on PRs, and by `workflow_dispatch`.
   - Find the run: `gh run list -R SimonBarnett/bobiverse --workflow build-jeeves.yml --branch main --limit 5`.
   - Require `conclusion=success` and `headSha` == the intended merge SHA.
   - Jeeves artifact holds `jeeves.exe`, `jeeves.exe.sha256`, `MANIFEST.json` (FR #6395):
     `source_commit`, `exe_sha256`, `exe_size_bytes`, `build_time_utc`, `workflow_run_id`.
2. **Catalog `!build` (release / pack path, FR #8490 / PR #8491).** Bare `!build` lists the numbered catalog;
   `!build dry-run n [version] [ref]` plans; `!build n [version] [ref]` runs suites -> pack -> export -> prerelease
   -> install targets. Old `!build owner/repo ...` is refused. Syntax/auto-version/catalog-fallback changes are
   pending in FR #8770; read `!help build` live before quoting syntax.
   Success = `BUILD ok ... id=b-...` with pack/release true; failure files `release-blocker:` issues.
   Re-run only after those blockers close; never loop `!build` while they are open.

## Build receipt (required before handing to install)

Record, from the run itself (never from memory or a chat claim):

- component (jeeves / worker / ear / tray / airc / msi), repo, **source SHA** (full), PR/FR numbers covered
- workflow name + run id + conclusion, artifact name
- artifact SHA-256 + size (from `MANIFEST.json` or `*.sha256`; re-hash the downloaded file and compare)
- what it supersedes (currently installed SHA/hash) so install has a rollback target
- open caveats (e.g. other workflows red on that SHA and why they do not affect this component)

Download into a scratch folder: `gh run download <run-id> -R SimonBarnett/bobiverse -n <artifact> -D <dir>`,
then `Get-FileHash -Algorithm SHA256` (or `sha256sum`) and compare to the manifest. Mismatch = stop.

## Batching

- Pool fixes and fixes Si is actively waiting on: build/hand off immediately.
- Other worker fixes: batch for up to about 2 hours into one install so a machine is touched once.
- One receipt per install batch; list every FR it covers.

## Release rules

- A release always ships **all three MSIs** (bob, jeeves, airc) from one green SHA.
- Prerelease first. Promoting to Latest / publishing needs **Si's explicit go** for that version.
- CI-built MSIs carry CI versions; say so in the release notes rather than renaming.

## Verify

Receipt complete, hash re-computed and matching, run green on the exact SHA, and (if a catalog build)
`BUILD ok` seen. Then hand to `bobiverse-jeeves-agent-install`; after install it runs the monitor post-check.

## Stop rules

- Red main for that component, hash mismatch, missing manifest, or SHA not on main: stop and report.
- Never publish/promote a release, or send `!build`, without the operator's explicit go for that SHA/version.
- Never paste tokens or PATs into commands shown in chat; rely on the host's existing gh auth.

# Bobiverse BUILD job (FR #4006 / #4025)

Deterministic, **zero AI tokens**. Jeeves ops run `!build`; each repo ships `.bobiverse/build.yml`.

## Recipe (`.bobiverse/build.yml`)

| Field | Meaning |
|---|---|
| `machine` | Build host (bobiverse: `ionos`) |
| `baseline` | Usually `last_release_tag` |
| `suites[]` | `{name, cmd, cwd, env, timeout}` — run at ref and baseline |
| `pack` | Commands + artifact globs (+ `.sha256`) |
| `release` | `github-prerelease`, never Latest |
| `install_test` | Optional follow-on (WP3) |
| `cache_dirs` | Persistent download caches |
| `max_parallel_builds` | Machine cap (default 1) |

## Classification

| Kind | Rule |
|---|---|
| `new_regression` | Fails at ref, passes at baseline |
| `pre_existing` | Fails at both |
| `flaky` | Ref fail, one solo rerun at ref passes |
| `step_failure` | Pack/fetch/upload step failed |

New regressions and step failures → one intake issue each (`feature-request` + `release-blocker`), deduped by test id / error signature.

## IRC

```
!build <owner/repo>[,owner/repo...] <version> [ref]
!build dry-run <owner/repo> <version> [ref]
!build status [owner/repo]
!build cancel <owner/repo>
```

Ops only (simon / bob-* ears). No recipe → refuse. Same repo already building → refuse with running id.

## Work packages

- **WP1:** recipe, classify, lock, `!build` CommandSpec/help, dry-run decide, docs
- **WP2 (FR #4025):** live runner on recipe machine (below)
- **WP3:** optional INSTALL-TEST job

## WP2 runner (FR #4025)

Deterministic, injectable, **zero AI tokens**. Module: `common/scripts/bobiverse_build.py`.

### Flow

1. Chair `!build` decides and announces `BUILD v1 repos=... version=... ref=...` on `#bobiverse`.
2. Recipe machine (bobiverse: `ionos` / DIGEST_ID_FOLD `win-mpre8vi4u6u`) consumes the wire via `consume_build_v1` and enqueues `home/build-queue/*.json` (spawn/pack outside the chair process).
3. `BuildRunner.run()`:
   - Ensures `work_dir` / `log_dir` and recipe `cache_dirs` under `work_dir/cache` (override root with env `BOBIVERSE_DOWNLOAD_CACHE`).
   - Resolves baseline (injectable; default stub tag `baseline`).
   - Runs each suite at ref and at baseline; one solo rerun on ref failure; classifies.
   - Hard timeouts (FR #3965 class) via `run_command` --- kill + `timed_out` => `step_failure`.
   - Files one intake issue per `new_regression` / `step_failure` with labels `feature-request` + `release-blocker` (`file_blocker_or_dedupe`; comment if open duplicate).
   - **Pack and release only when there are no new_regression/step_failure blockers** (pre_existing / flaky do not block).
   - Pack renders `{{version}}` / `{{out_dir}}` / `{{ref}}`; verifies artifact names; optional assert cmd.
   - Release target `github-prerelease` with recipe `never_latest: true` => prerelease, never Latest.
   - Zips `log_dir` to `build-logs-{version}.zip`; announce summary lines for `#bobiverse`.

### Test doubles

- `FakeGitHubFiler` --- in-memory `list_open_issues` / `create_issue` / `comment`.
- GitHubFiler --- live `gh issue list/create/comment` (injectable `gh_runner` for tests; MRB #4072).
- Inject `run_command_fn`, `pack_fn`, `release_fn`, `baseline_resolver` on `BuildRunner`.

### Helpers

- `render_template`, `parse_build_v1_route`, `fold_build_machine`, `is_recipe_build_machine`
- `SuiteRunResult`, `BuildReport`, `run_command(..., runner=subprocess)`

## CLI drain (FR #4025)

python common/scripts/run_bobiverse_build.py --queue-dir <home>/build-queue --repo-root <root> [--fake-filer] executes one enqueued BUILD v1 job via BuildRunner.

## WP stacking (implementer)

Later BUILD work packages reuse earlier WP helpers on tip --- do not reimplement shared pieces.

- After WP2 (`FakeGitHubFiler`, `file_blocker_or_dedupe`, machine fold) is on `main`, rebase WP3 (INSTALL-TEST / `!installtest`) onto that tip and call the tip APIs instead of restoring old helper signatures.
- Collapse UTF-16 double-spaced saved sources before merge when a WP tip was saved that way.

(MRB #4086 moved out of `harvest` wrong-book; product home is this doc / skill `bobiverse-build` when present.)


# Bobiverse BUILD job (FR #4006 / #4025 / #4026)

Deterministic, **zero AI tokens**. Jeeves ops run `!build`; each repo ships `.bobiverse/build.yml`.

Agent playbook: `jeeves/.grok/skills/bobiverse-build/SKILL.md` (FR #4038) --- how to read BUILD announce lines and when to `!build` again. Chair stub: `!help build` / `bobiverse-jeeves-commands`.

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
| `new_regression` | `FAILED`/`ERROR` nodeid at ref not in baseline (FR #5121 set difference) |
| `pre_existing` | Identical failing nodeid set at ref and baseline (not suite exit alone) |
| `flaky` | New nodeid at ref, one solo rerun at ref passes |
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
- **WP3 (FR #4026):** optional INSTALL-TEST job (`!installtest`) --- see below

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

## WP3 INSTALL-TEST (FR #4026)

Optional follow-on after a successful BUILD. Ops-only, **zero AI tokens**.

### IRC

```
!installtest <owner/repo> <version> [tag]
!installtest dry-run <owner/repo> <version> [tag]
```

Chair decides + PM; announces `INSTALLTEST v1 repo=... version=... tag=...` on `#bobiverse` when accepted.
Requires `install_test` in `.bobiverse/build.yml` (machine, products, optional `msiexec_extra`).
Runs on `install_test.machine` (bobiverse: `ionos` / DIGEST_ID_FOLD).

### Runner (`InstallTestRunner`)

1. Resolve product MSIs (`{product}-{version}.msi`) via injectable `asset_resolver` (default: ProgramData build-work/releases).
2. `msiexec /i /qn /l*v` each MSI (+ recipe `msiexec_extra` tokens).
3. Post-check keys: `service_up`, `sasl_ok`, `channels_ok`, `seat_ack` (injectable `postcheck_fn`).
4. On failure: `classify_step_failure` + WP2 `file_blocker_or_dedupe` (`feature-request` + `release-blocker`).
5. Zip evidence to `installtest-{version}-evidence.zip`; announce PASS/FAIL.

### Test doubles

Reuse WP2 `FakeGitHubFiler` / `file_blocker_or_dedupe` / `is_recipe_build_machine` / `classify_step_failure`.
Inject `msiexec_fn`, `postcheck_fn`, `asset_resolver`, `filer` on `InstallTestRunner`.

### Queue / drain (MRB #4085)

Chair announces `INSTALLTEST v1` then `consume_installtest_v1` enqueues `home/build-queue/installtest-*.json` when local matches `install_test.machine` (same fold as BUILD). Drain:

`python common/scripts/run_bobiverse_installtest.py --queue-dir <home>/build-queue --repo-root <root> [--fake-filer]`


## WP stacking (implementer)

Later BUILD work packages reuse earlier WP helpers on tip --- do not reimplement shared pieces.

- After WP2 (`FakeGitHubFiler`, `file_blocker_or_dedupe`, machine fold) is on `main`, rebase WP3 (INSTALL-TEST / `!installtest`) onto that tip and call the tip APIs instead of restoring old helper signatures.
- Collapse UTF-16 double-spaced saved sources before merge when a WP tip was saved that way.

(MRB #4086 moved out of `harvest` wrong-book; product home is this doc / skill `bobiverse-build` when present.)



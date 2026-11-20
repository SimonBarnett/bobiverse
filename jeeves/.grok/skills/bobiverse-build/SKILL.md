---
name: bobiverse-build
description: >
  Deterministic zero-token BUILD job (!build): recipe contract, classification,
  dry-run vs live, how to read #bobiverse BUILD announce lines, when to re-run
  after release-blocker closes. Use for !build, BUILD v1, build.yml, pack/release,
  FakeGitHubFiler, or /bobiverse-build.
---

# bobiverse-build

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> File every issue/FR/bug/gap in the same turn via intake (`https://bob.ntsa.uk/bob/v1/intake`):
> `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> End sessions with `Invoke-BobiverseHarvest.ps1 -Repo <job-repo> -Summary ... -Lesson ...` then `-Flush`.
> Bob fleet lessons use `-Repo SimonBarnett/bobiverse`. Never put tokens, passwords, SASL/NickServ secrets, keys or private hostnames in a filing or skill.

Focused playbook for the **BUILD** job (FR #4006 WP1, FR #4025 WP2, skill gap FR #4038, catalog FR #8490).
Authoritative long form: `docs/bobiverse-build.md`. Command surface stub: `bobiverse-jeeves-commands` (`!help build`).
Code: `common/scripts/bobiverse_build.py`, drain CLI `common/scripts/run_bobiverse_build.py`, catalog `common/scripts/builds_catalog.py`.

## Zero-token rule (CAST IRON)

BUILD is **deterministic and uses zero AI tokens**. The chair parses/decides/announces; the recipe machine runs suites, classifies, files blockers, packs, exports, and installs. Never spawn an agent seat to do the build. Agents may **read** results and open FRs for gaps; they do not replace the runner.

## Recipe contract (`.bobiverse/build.yml`)

Each repo that supports `!build` ships this file at the repo root.

| Field | Meaning |
|---|---|
| `machine` | Build host (bobiverse: `flamingo`; digest id is `flamingo`) |
| `baseline` | Usually `last_release_tag` |
| `suites[]` | `{name, cmd, cwd, env, timeout}` run at **ref** and **baseline** |
| `pack` | Commands + artifact globs (+ `.sha256`); templates `{{version}}` / `{{out_dir}}` / `{{ref}}` |
| `release` | `github-prerelease` with `never_latest: true`. Re-running the same `VERSION` uploads onto the existing pre-release (`gh release upload --clobber`); it does not fail because the tag already exists (FR #7086). A full non-pre release or Latest tag is still refused. |
| `install_test` | Optional follow-on (WP3 / FR #4026) |
| `cache_dirs` | Persistent download caches under work_dir (or `BOBIVERSE_DOWNLOAD_CACHE`) |
| `max_parallel_builds` | Machine cap (default 1) |

No recipe => chair refuses. Same repo already building => refuse with running id.

## Classification

| Kind | Rule | Blocks pack/release? |
|---|---|---|
| `new_regression` | Pytest `FAILED`/`ERROR` nodeid at ref but not at baseline (set difference; FR #5121). Brand-new failing tests count. Red suite with no parseable nodeids fail-closed. | **Yes** --- one intake issue (`feature-request` + `release-blocker`), deduped by test id |
| `step_failure` | Pack/fetch/upload/timeout step failed | **Yes** --- same filing path |
| `pre_existing` | Same failing nodeid set at ref and baseline. **Never** treat suite-exit-only red as pre_existing while baseline is also red (that hid v1.0.5 117→132). | No |
| `flaky` | New nodeid at ref, one solo rerun at ref passes | No |

Hard timeouts (FR #3965 class) via `run_command` kill + `timed_out` => `step_failure`.

## Catalog UX (FR #8490)

| Mode | Who | What happens |
|---|---|---|
| bare `!build` | Chair (ops) | Numbered list from GET `/bob/v1/builds` (`builds-catalog.json` on digest home). Shows name, yml, install, dep, version, ref, output. |
| `!build n [version] [ref] [--tests-only]` | Chair then recipe machine | Select catalog entry `n`. Version/ref override catalog defaults (numeric `x.y.z` / `x.y.z.w`, #4186). Wire `BUILD v1 ... output=... install=...`. Runner: suites → pack → **export** artifacts to `output` → prerelease → **install** (`machinename` or `fleet` via `registered-machines.json`). Local: msiexec via recipe `install_test` against exported MSIs. Remote: `BUILD_INSTALL` queue jobs. Offline / no `install_test`: WARN-and-continue. `dep` is documentation only. |
| `!build dry-run n ...` | Chair (ops) | Plan only (includes install/output); nothing published. |
| `!build status\|cancel\|preflight\|tests-only n` | Chair / recipe | Same verbs, keyed by catalog index `n`. |
| Old `!build owner/repo ...` | — | **Refused**; use the numbered list. |

Ops only (simon / bob-* ears). Workers never see `!build` in `!help`.

Announce extras: `BUILD export ... output=... n=N`, `BUILD install ... targets=...`, `BUILD install queued|ok|fail|WARN ... machine=...`.

## Preflight (FR #6492)

`!build preflight <owner/repo>` announces `BUILDPREFLIGHT v1 repo=...` on `#bobiverse`. The recipe machine runs `run_bobiverse_build.py --preflight` and announces `build preflight: <name>=ok|missing ...` lines (never the token value). Setup steps: `bob/AGENTS.md` section Recipe machine BUILD setup.

## Reading BUILD announce / PM lines

Typical shapes (channel `#bobiverse` + ops PM from chair):

- **Route / start:** `BUILD v1 repos=owner/repo version=X ref=Y id=b-...` --- recipe machine consumes this. FR #5266: chair and ear both hear the wire, but O_EXCL `%ProgramData%\Bobiverse\build-routes\<id>.claimed` plus a machine-global `build-locks.json` and unique `build-work\<ver>-<job>` keep one runner; git stderr is in `result.json`. FR #6491: `id=` is always on the route; terminal `BUILD ok|fail ... id=` frees the chair `home/build-locks.json` by matching id; a stale chair lock (older than recipe max run) is released on the next `!build`. FR #6558: duplicate route claims log one line (id, marker path, age); id-less `h-` markers older than local `recipe_max_run_s` may reclaim under `.reclaim.lock` (never delete that lock); explicit `id=` claims stay permanent.
- **Dry-run plan:** lines starting `build dry-run:` (machine, suites, baseline, would classify, nothing published).
- **Success:** `BUILD ok <repo> version=... ref=... tag=... prerelease ... id=b-...` (pack+release ran; no new_regression/step_failure blockers).
- **Failure:** `BUILD fail <repo> version=... ref=... blockers=N pack=... release=... id=b-...` or `BUILD fail ... wrong machine id=b-...`. Chair frees `home/build-locks.json` when id matches (FR #6491); stale locks clear on the next `!build`.
- **Live progress (FR #6585):** while the runner is up, `#bobiverse` also gets `BUILD progress <repo> version=... ... id=...` lines (step start/end with elapsed, suite pass/fail/skip counts, `rerun N/M <nodeid> pass|fail`, and a heartbeat after 10 minutes idle). Rate-limited (~30s) and redacted; a failed post never fails the build. Terminal `BUILD ok|fail` shape is unchanged.
- **Status / usage / refuse:** `build status:`, `build: usage ...`, `build: no .bobiverse/build.yml`, lock refuse with running id.

Blocker issues filed by the runner: title like `release-blocker: <test_id> (<version>)`, labels `feature-request` + `release-blocker`. Re-hit comments: `BUILD re-hit <kind> for <test_id> ...`.

Drain one queued job on the recipe host:

```text
python common/scripts/run_bobiverse_build.py --queue-dir <home>/build-queue --repo-root <root> [--fake-filer]
```

## When to `!build` again

Re-run **after** the open `release-blocker` issues from the failed build are **closed** (fix merged + MRB, or confirmed false positive closed). Then:

1. Optional: bare `!build` then `!build dry-run n [version] [ref]` to confirm catalog entry/plan.
2. Live: `!build n [version] [ref]` (same or newer version/ref as intended release).
3. Read announce: need `BUILD ok ...` with pack/release true (and `BUILD export` when output is set) before treating the version as build-green.
4. Do **not** re-`!build` in a loop while blockers are still open --- that only re-hits and comments on the same issues.
5. `pre_existing` / `flaky` alone do not block pack; still investigate, but they are not the release-blocker gate.

WP3 INSTALL-TEST (FR #4026) remains available as a manual follow-on (`!installtest`); catalog `!build n` already drives local msiexec when `install_test` is present and queues remote `BUILD_INSTALL` jobs for fleet targets.

## Cross-links

- Docs: `docs/bobiverse-build.md`
- Chair help: `!help build` (ops) / skill `bobiverse-jeeves-commands` section `!build`
- Parent FR: #4006 (living umbrella --- do not `Closes` it from docs-only PRs); WP2 #4025; this skill book #4038; catalog #8490
- Tests: `common/tests/test_fr4006_build_job.py`, WP2 runner tests, `common/tests/test_fr8490_*.py`, `jeeves/tests/test_fr4038_bobiverse_build_skill.py`, `common/tests/test_fr6491_chair_build_lock_release.py` (FR #6491 chair lock release), `common/tests/test_fr7086_release_tag_already_exists.py` (FR #7086 idempotent pre-release)

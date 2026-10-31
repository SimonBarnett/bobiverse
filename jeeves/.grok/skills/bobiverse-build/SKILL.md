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

Focused playbook for the **BUILD** job (FR #4006 WP1, FR #4025 WP2, skill gap FR #4038).
Authoritative long form: `docs/bobiverse-build.md`. Command surface stub: `bobiverse-jeeves-commands` (`!help build`).
Code: `common/scripts/bobiverse_build.py`, drain CLI `common/scripts/run_bobiverse_build.py`.

## Zero-token rule (CAST IRON)

BUILD is **deterministic and uses zero AI tokens**. The chair parses/decides/announces; the recipe machine runs suites, classifies, files blockers, packs and releases. Never spawn an agent seat to do the build. Agents may **read** results and open FRs for gaps; they do not replace the runner.

## Recipe contract (`.bobiverse/build.yml`)

Each repo that supports `!build` ships this file at the repo root.

| Field | Meaning |
|---|---|
| `machine` | Build host (bobiverse: `ionos`; DIGEST_ID_FOLD accepts `win-mpre8vi4u6u`) |
| `baseline` | Usually `last_release_tag` |
| `suites[]` | `{name, cmd, cwd, env, timeout}` run at **ref** and **baseline** |
| `pack` | Commands + artifact globs (+ `.sha256`); templates `{{version}}` / `{{out_dir}}` / `{{ref}}` |
| `release` | `github-prerelease` with `never_latest: true` |
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

## Dry-run vs live

| Mode | Who | What happens |
|---|---|---|
| `!build dry-run <repos> <version> [ref]` | Chair (ops) | Decide only: print plan lines (would classify, would file blockers, would announce). **Nothing published**, no queue job. |
| `!build <repos> <version> [ref]` | Chair then recipe machine (version must be numeric x.y.z / x.y.z.w, else refused, #4186) | Chair announces wire `BUILD v1 repos=... version=... ref=...` on `#bobiverse` (and PM reply lines). Recipe host `consume_build_v1` enqueues `home/build-queue/*.json`; `BuildRunner.run()` executes suites/pack/release. |
| `!build status [owner/repo]` | Chair | Running lock id or none. |
| `!build cancel <owner/repo>` | Chair | Clear lock / cancel path. |

Ops only (simon / bob-* ears). Workers never see `!build` in `!help`.

## Reading BUILD announce / PM lines

Typical shapes (channel `#bobiverse` + ops PM from chair):

- **Route / start:** `BUILD v1 repos=owner/repo version=X ref=Y [id=b-...]` --- recipe machine consumes this. FR #5266: chair and ear both hear the wire, but O_EXCL `%ProgramData%\Bobiverse\build-routes\<id>.claimed` plus a machine-global `build-locks.json` and unique `build-work\<ver>-<job>` keep one runner; git stderr is in `result.json`.
- **Dry-run plan:** lines starting `build dry-run:` (machine, suites, baseline, would classify, nothing published).
- **Success:** `BUILD ok <repo> version=... ref=... tag=... prerelease ...` (pack+release ran; no new_regression/step_failure blockers).
- **Failure:** `BUILD fail <repo> version=... ref=... blockers=N pack=... release=...` or `BUILD fail ... wrong machine`.
- **Status / usage / refuse:** `build status:`, `build: usage ...`, `build: no .bobiverse/build.yml`, lock refuse with running id.

Blocker issues filed by the runner: title like `release-blocker: <test_id> (<version>)`, labels `feature-request` + `release-blocker`. Re-hit comments: `BUILD re-hit <kind> for <test_id> ...`.

Drain one queued job on the recipe host:

```text
python common/scripts/run_bobiverse_build.py --queue-dir <home>/build-queue --repo-root <root> [--fake-filer]
```

## When to `!build` again

Re-run **after** the open `release-blocker` issues from the failed build are **closed** (fix merged + MRB, or confirmed false positive closed). Then:

1. Optional: `!build dry-run owner/repo <version> [ref]` to confirm recipe/plan.
2. Live: `!build owner/repo <version> [ref]` (same or newer version/ref as intended release).
3. Read announce: need `BUILD ok ...` with pack/release true before treating the version as build-green.
4. Do **not** re-`!build` in a loop while blockers are still open --- that only re-hits and comments on the same issues.
5. `pre_existing` / `flaky` alone do not block pack; still investigate, but they are not the release-blocker gate.

WP3 INSTALL-TEST (FR #4026), when present in the recipe, is a separate follow-on after a successful BUILD --- `!installtest` announces `INSTALLTEST v1`, enqueues `installtest-*.json`, drain via `run_bobiverse_installtest.py`; do not confuse it with re-running BUILD.

## Cross-links

- Docs: `docs/bobiverse-build.md`
- Chair help: `!help build` (ops) / skill `bobiverse-jeeves-commands` section `!build`
- Parent FR: #4006 (living umbrella --- do not `Closes` it from docs-only PRs); WP2 #4025; this skill book #4038
- Tests: `common/tests/test_fr4006_build_job.py`, WP2 runner tests, `jeeves/tests/test_fr4038_bobiverse_build_skill.py`

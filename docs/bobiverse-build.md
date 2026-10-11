# Bobiverse BUILD job (FR #4006)

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

- **WP1 (this):** recipe, classify, lock, `!build` CommandSpec/help, dry-run decide, docs
- **WP2:** ear on recipe machine runs suites/pack/release + auto-issues
- **WP3:** optional INSTALL-TEST job

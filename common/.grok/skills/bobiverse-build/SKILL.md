---
name: bobiverse-build
description: >
  Deterministic zero-token BUILD job (!build): recipe contract, classification,
  dry-run vs live, how to read #bobiverse BUILD announce lines, when to re-run
  after release-blocker closes. Companion harvest stub under common/; canonical
  book also lives at jeeves/.grok/skills/bobiverse-build. Use for !build, BUILD v1,
  build.yml, pack/release.
github: https://github.com/SimonBarnett/bobiverse
---

# bobiverse-build (common harvest companion)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; POST https://bob.ntsa.uk/bob/v1/intake; offline it is
>    queued locally and retried):
>    .\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"
>    (-Kind issue|fr|skill|harvest; always pass an explicit -Repo owner/name).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    .\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"
>    then .\scripts\Invoke-BobiverseHarvest.ps1 -Flush to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

Canonical playbook: jeeves/.grok/skills/bobiverse-build/SKILL.md and docs/bobiverse-build.md.

## Harvested lessons (intake)

- BUILD suite command-not-found (Win 9009 / is not recognized): environment failure, no release-blocker comments; prepend BOBIVERSE_PYTHON dir+Scripts to PATH. FR #6490 / PR #6493.
- Live `#bobiverse` progress during BUILD (FR #6585): runner writes `progress.jsonl`; ear watcher posts `BUILD progress ... version=... id=...` (steps, suite counts, solo reruns, 10m heartbeat). Rate-limit ~30s; redact secrets; sink failure never fails the build; terminal BUILD ok/fail unchanged.
- Build-work root (FR #6655): `BOBIVERSE_BUILD_WORK_DIR` else alias `BOBIVERSE_BUILD_WORK` else `%ProgramData%/Bobiverse/build-work`; preflight `work_dir_free` refuses under `BOBIVERSE_BUILD_WORK_MIN_FREE_GB` (default 2); prune finished/dead siblings keep `BOBIVERSE_BUILD_WORK_KEEP` (default 2), never active names / recent heartbeats.
- Ear BUILD progress relay (FR #6654): `BuildProgressRelay` tails `progress.jsonl` with durable `.pos` offset (restart-safe), flood-paced posts, logged relay/skip reasons; no secrets or full paths on channel.
- Same-VERSION `!build` when `vX.Y.Z` already exists: upload `--clobber` onto the existing pre-release; do not file `step:release` for "tag already exists". Full/Latest releases still fail closed. FR #7086.

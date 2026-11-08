# OpenCode Windows seat readiness (FR #6240)

Seat `marchhare-22088` is OpenCode (`opencode/beam-free`), not Grok. It started in `C:\ai\bob\worker`. Headless `opencode run` then auto-rejected `external_directory` for the job worktree and for the run-dir outbox. That denial stands. This change does not grant `external_directory`, does not pass `--auto`, and does not treat a test that expected `allow` as consent.

Public CLI reference used here: [OpenCode CLI](https://dev.opencode.ai/docs/cli/) documents `opencode run --dir` as the directory to run in, and does not list `--interactive` on `opencode run`. Headless `opencode run` auto-rejects an `ask` (the live text was `permission requested: external_directory (...); auto-rejecting`). This agent did not execute the OpenCode 1.19.5 binary.

`BOB_HOME` may be empty. `BOB_OUTBOX` is the run file the worker sets. Writing that file from inside OpenCode is still outside the project directory, so headless mode will still auto-reject it until a person answers `external_directory` in the interactive TUI (`opencode`, not `opencode run`).

## What the worker does

- `gh auth status` before the model starts. If the CLI is not logged in, the seat does not start and logs `gh_auth_missing`. The status body is not logged. No `hosts.yml` read and no token search.
- On each assign it records `<BOB_JOB_WORKTREE_BASE or BOB_BRIDGE_HOME\worktrees>\<repo>\<fr-N>` in the run file `opencode-project-dir.txt`. It does not create that folder.
- The next `opencode run` passes `--dir` only when that recorded folder exists and its canonical path is not a credential store (`C:/passwords`, `C:/Users/.../.config/gh`, and a symlink to either, included). A missing folder skips the model for that line and prints `worktree_absent`. That is not DONE.
- There is no seat-wide `BOB_OPENCODE_DIR`. A stale manual directory is not the project context.

PR #6241 (on main) is the preflight script: relaunch with the job worktree as cwd, or ask for narrow consent. This launch follows that. It does not add a second copy of that script and it does not widen consent.

## Parent handoff

Do not restart or stop OpenCode seat `marchhare-22088` from this note, and do not touch any other seat. No install and no auth change is in this PR.

After review, rebuild `bob-worker.exe` only (`scripts\Build-BobWorker.ps1`). A later OpenCode start, by a person:

1. `gh auth status` must show the CLI logged in. If it says `gh auth login`, a person runs that. Do not open `hosts.yml` or `C:\passwords`.
2. The job worktree must already exist at `Get-BobiverseJobWorktreePath` (for bobiverse #6147 that is `...\worktrees\bobiverse\fr-6147` when `BOB_BRIDGE_HOME` or `BOB_JOB_WORKTREE_BASE` is the base already used on the box). The worker will not create it and will not allow `external_directory` so the model can create it.
3. Confirm a child `opencode run` for that job includes `--dir` of that folder and does not include `--auto`. Confirm a missing worktree prints `worktree_absent` and does not post DONE. Confirm a missing `gh auth status` exits with `gh_auth_missing` and does not post DONE.

Windows search inside the seat is `Get-ChildItem` and `Select-String`. If OpenCode prints `auto-rejecting`, do not retry a wider path.

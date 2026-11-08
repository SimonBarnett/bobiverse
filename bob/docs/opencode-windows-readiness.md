# OpenCode Windows seat readiness (FR #6240)

Seat `marchhare-22088` is OpenCode (`opencode/beam-free`), not Grok. It started in `C:\ai\bob\worker`. Headless `opencode run` then auto-rejected `external_directory` for the job worktree and for the run-dir outbox. That denial stands. This change does not grant `external_directory`, does not pass `--auto`, and does not treat a test that expected `allow` as consent.

Public CLI reference used here: [OpenCode CLI](https://dev.opencode.ai/docs/cli/) documents `opencode run --dir` as the directory to run in, and does not list `--interactive` on `opencode run`. Headless `opencode run` auto-rejects an `ask` (the live text was `permission requested: external_directory (...); auto-rejecting`). This agent did not execute the OpenCode 1.19.5 binary.

`BOB_HOME` may be empty. `BOB_OUTBOX` is the run file the worker sets. Writing that file from inside OpenCode is still outside the project directory. Headless `opencode run` auto-rejects that ask. There is no official evidence that an Allow answered in the interactive TUI is honored by a later `opencode run`. Outbox consent stays a human gate. This change does not claim that gate is solved.

## What the worker does

- `gh auth status` before the model starts. If the CLI is not logged in, the seat does not start and logs `gh_auth_missing`. The status body is not logged. No `hosts.yml` read and no token search.
- The job worktree base follows `Get-BobiverseJobWorktreeBase`: `BOB_JOB_WORKTREE_BASE`, else `BOB_BRIDGE_HOME\worktrees` when the bridge is not a drive root, else `<data-drive>\ai\worktrees` (non-system `D:\` when that fixed disk is present, else the system drive). A drive-root base is refused. The worker does not create the folder.
- On each assign the path is `<base>\<repo-leaf>\<fr-N>` (`owner/repo` or a bare repo leaf). The run file `opencode-project-dir.txt` is written only when that directory already exists and is not a credential path (`C:/passwords`, `C:/Users/.../.config/gh`, and a symlink to either).
- A missing directory, a drive-root base, a forbidden path, or an assign whose repo leaf is `..` or empty is NACKed (`worktree-absent`, `worktree-base-refused`, `opencode-dir-forbidden`, or `job-context-malformed`) before ACK. The line is not injected and the chair does not keep the job. That is not DONE.
- If the folder disappears after ACK, the launch wrapper NACKs the same way and does not start `opencode run` for that line. An assign with no recorded directory is not run from `C:\ai\bob\worker`.
- There is no seat-wide `BOB_OPENCODE_DIR`. A stale manual directory is not the project context. There is no `external_directory` allow and no `OPENCODE_CONFIG` grant.

PR #6241 (on main) is the preflight script: relaunch with the job worktree as cwd, or ask for narrow consent. This launch follows that. It does not add a second copy of that script and it does not widen consent.

## Parent handoff

Do not restart or stop OpenCode seat `marchhare-22088` from this note, and do not touch any other seat. No install and no auth change is in this PR.

After review, rebuild `bob-worker.exe` only (`scripts\Build-BobWorker.ps1`). A later OpenCode start, by a person:

1. `gh auth status` must show the CLI logged in. If it says `gh auth login`, a person runs that. Do not open `hosts.yml` or `C:\passwords`.
2. The job worktree must already exist at `Get-BobiverseJobWorktreePath`. With no base env that is `<data-drive>\ai\worktrees\<repo>\<fr-N>`. The worker will not create it. A missing folder is NACKed `worktree-absent` before ACK.
3. Confirm a child `opencode run` for an existing job folder includes `--dir` of that folder and does not include `--auto`. Confirm a missing worktree posts `NACK ... worktree-absent` and does not post ACK or DONE. Confirm a missing `gh auth status` exits with `gh_auth_missing` and does not post DONE. Outbox writes from headless OpenCode are still unsolved.

Windows search inside the seat is `Get-ChildItem` and `Select-String`. If OpenCode prints `auto-rejecting`, do not retry a wider path.

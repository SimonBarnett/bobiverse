# OpenCode Windows seat readiness (FR #6240)

Installed OpenCode 1.19.5 seats start in `C:\ai\bob\worker` and call headless `opencode run`. That mode auto-rejects `external_directory` asks. The installed CLI has `opencode run --dir <directory>`. It does not have `--interactive`. `--auto` would approve asks that are not denied, and this worker never passes it.

`BOB_HOME` may be empty. That is not a failure. `BOB_OUTBOX` is the seat run file `...\worker\run\worker-<nick>-<id>\outbox.txt`. The worker sets it. The model appends ACK/DONE there and does not read credential files.

## What the worker does

- Before the model starts, it runs `gh auth status` and nothing else. If that is not a logged-in status, the seat does not start and logs `opencode-ready: blocked gh_auth_missing`. It does not read `hosts.yml`, search other trees, or copy a token.
- `BOB_OPENCODE_DIR`, when set to an existing directory that is not a credential path, is passed as `opencode run --dir`. That makes the assigned worktree the project directory so git and file tools there are not `external_directory`.
- The worker writes `opencode-seat.json` in the run directory and points `OPENCODE_CONFIG` at it. `external_directory` for `*` stays `ask` (headless still auto-rejects those). Only `<run-dir>\*` is `allow`, so the outbox protocol can run. `.config\gh`, password folders, and other repos are not in that allow.

PR #6241 is a separate preflight script. This change is the launch the seat actually runs. It does not copy that script.

## Parent handoff (do not run this from an agent)

Do not restart or stop the live Grok seat `marchhare-16096`. There is no install or auth change in this PR.

When a new OpenCode seat is wanted, on that Windows user:

1. `gh auth status` must print that the CLI is logged in. If it says `gh auth login`, a person runs `gh auth login` in that user. Do not open `C:\Users\Administrator\.config\gh\hosts.yml` and do not read `C:\passwords`.
2. Create the job worktree with `Get-BobiverseJobWorktreePath` (for example `...\worktrees\bobiverse\fr-6147`).
3. Start the seat with `BOB_OPENCODE_DIR` set to that worktree. The rebuilt `bob-worker.exe` then uses `opencode run --dir`.
4. Rebuild `bob-worker.exe` from this head first (`scripts\Build-BobWorker.ps1`). No tray or fuel change is in this PR.

Windows file search inside the seat is `Get-ChildItem` and `Select-String`, not `grep` or `head`. If OpenCode prints `external_directory` and `auto-rejecting`, that denial stands. Do not retry a wider path and do not add `--auto`.

Native check still required on Windows after the rebuild: one OpenCode start with `gh auth status` already logged in and `BOB_OPENCODE_DIR` pointing at a real worktree, then confirm the child command contains `--dir` and not `--auto`, and that a missing `gh auth status` refuses the start with `gh_auth_missing` and no DONE.

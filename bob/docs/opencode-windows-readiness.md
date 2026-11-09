# OpenCode Windows seat readiness (FR #6240 / FR #6320 / FR #6328)

Seat `marchhare-22088` is OpenCode (`opencode/beam-free`), not Grok. It started in `C:\ai\bob\worker`. Headless `opencode run` then auto-rejected `external_directory` for the job worktree and for the run-dir outbox. That denial stands. This change does not grant `external_directory`, does not pass `--auto`, and does not treat a test that expected `allow` as consent.

Public CLI reference used here: [OpenCode CLI](https://dev.opencode.ai/docs/cli/) documents `opencode run --dir` as the directory to run in, and does not list `--interactive` on `opencode run`. Headless `opencode run` auto-rejects an `ask` (the live text was `permission requested: external_directory (...); auto-rejecting`). This agent did not execute the OpenCode 1.19.5 binary.

`BOB_HOME` may be empty. `BOB_OUTBOX` is the run file the worker sets. Writing that file from inside OpenCode is still outside the project directory. Headless `opencode run` auto-rejects that ask. There is no official evidence that an Allow answered in the interactive TUI is honored by a later `opencode run`. Outbox consent stays a human gate. This change does not claim that gate is solved.

## What the worker does

- `gh auth status` before the model starts. If the CLI is not logged in, the seat does not start and logs `gh_auth_missing`. The status body is not logged. No `hosts.yml` read and no token search.
- The job worktree base follows `Get-BobiverseJobWorktreeBase`: `BOB_JOB_WORKTREE_BASE`, else `BOB_BRIDGE_HOME\worktrees` when the bridge is not a drive root, else `<data-drive>\ai\worktrees` (non-system `D:\` when that fixed disk is present, else the system drive). The path is canonicalized first, so `D:\ai\..` is a drive root and is refused. FR #6320 / #6328: on assign the worker creates `Get-BobiverseJobWorktreePath` (idempotent `git worktree add` from the machine clone) before ACK; create runs off the IRC socket read thread with bounded git timeouts so PING stays responsive; a create failure NACKs `worktree-create-failed:<class>` with no ACK.
- A job is one `FROM` message with one id. The standing prompt is not a job; the example `FR SimonBarnett/a-search#637` in that prompt does not NACK and does not stop the model. Each accepted assign is injected as `@@BOBJOB1|key|directory|FROM ...`. `inject_console` runs that through `one_line`, which turns tabs into spaces, so the separator is a pipe. A line that loses that frame is NACKed and is not started in the worker folder. There is no shared `opencode-project-dir.txt`.
- A drive-root base, a forbidden path, or a `..` / empty repo leaf is NACKed before ACK. A missing directory is created first off the IRC read thread (FR #6320 / #6328); only a create failure NACKs `worktree-create-failed:<class>`. Two job ids in one message, or several assigns collapsed by the flood guard, are NACKed `job-context-ambiguous` with no ACK. That is not DONE.
- If the folder disappears after ACK, the launch NACKs that message's key and a later copy of the same assign is judged again. Headless outbox DONE stays denied. This does not grant a bypass.
- There is no seat-wide `BOB_OPENCODE_DIR`. A stale manual directory is not the project context. There is no `external_directory` allow and no `OPENCODE_CONFIG` grant.

PR #6241 (on main) is the preflight script: relaunch with the job worktree as cwd, or ask for narrow consent. This launch follows that. It does not add a second copy of that script and it does not widen consent.

## Parent handoff

Do not restart or stop OpenCode seat `marchhare-22088` from this note, and do not touch any other seat. No install and no auth change is in this PR.

After review, rebuild `bob-worker.exe` only (`scripts\Build-BobWorker.ps1`). A later OpenCode start, by a person:

1. `gh auth status` must show the CLI logged in. If it says `gh auth login`, a person runs that. Do not open `hosts.yml` or `C:\passwords`.
2. On assign the worker creates `Get-BobiverseJobWorktreePath` when missing (FR #6320 / #6328). With no base env that is `<data-drive>\ai\worktrees\<repo>\<fr-N>`. Creation is idempotent (`git worktree add` from the machine clone / install root for bobiverse) and runs off the IRC read thread with bounded timeouts. A create failure NACKs `worktree-create-failed:<class>` before ACK. Credential paths stay refused.
3. Confirm a child `opencode run` for that job folder includes `--dir` of that folder and does not include `--auto`. Confirm a create failure posts `NACK ... worktree-create-failed:` and does not post ACK or DONE. Confirm a missing `gh auth status` exits with `gh_auth_missing` and does not post DONE. Outbox writes from headless OpenCode are still unsolved.

Windows search inside the seat is `Get-ChildItem` and `Select-String`. If OpenCode prints `auto-rejecting`, do not retry a wider path.

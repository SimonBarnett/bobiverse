# OpenCode Windows seat readiness (FR #6240 / #6320 / #6333)

Seat `marchhare-22088` is OpenCode (`opencode/beam-free`), not Grok. It started in `C:\ai\bob\worker`. Headless `opencode run` then auto-rejected `external_directory` for the job worktree and for the run-dir outbox. That denial stands. This change does not grant `external_directory`, does not pass `--auto`, and does not treat a test that expected `allow` as consent.

Public CLI reference used here: [OpenCode CLI](https://dev.opencode.ai/docs/cli/) documents `opencode run --dir` as the directory to run in, and does not list `--interactive` on `opencode run`. Headless `opencode run` auto-rejects an `ask` (the live text was `permission requested: external_directory (...); auto-rejecting`). This agent did not execute the OpenCode 1.19.5 binary.

`BOB_HOME` may be empty. FR #6333: for OpenCode jobs the launch wrapper sets `$env:BOB_OUTBOX` to `<worktree>\.bob\outbox.txt` (inside `opencode run --dir`), so headless runs can append ACK/DONE/GIVEUP without an `external_directory` grant. The worker still ACK-on-receipt via the run-dir outbox; it also tails the in-worktree file and forwards only well-formed job PRIVMSG lines for the assigned key (duplicate ACK is deduped). `.bob/` is appended to `.git/info/exclude` (not a committed `.gitignore`). Never `--auto`, never `external_directory` allow rules.

## What the worker does

- `gh auth status` before the model starts. If the CLI is not logged in, the seat does not start and logs `gh_auth_missing`. The status body is not logged. No `hosts.yml` read and no token search.
- The job worktree base follows `Get-BobiverseJobWorktreeBase`: `BOB_JOB_WORKTREE_BASE`, else `BOB_BRIDGE_HOME\worktrees` when the bridge is not a drive root, else `<data-drive>\ai\worktrees` (non-system `D:\` when that fixed disk is present, else the system drive). The path is canonicalized first, so `D:\ai\..` is a drive root and is refused. FR #6320: on assign the worker creates `Get-BobiverseJobWorktreePath` (idempotent `git worktree add` from the machine clone) before ACK; a create failure NACKs `worktree-create-failed:<class>` with no ACK.
- A job is one `FROM` message with one id. The standing prompt is not a job; the example `FR SimonBarnett/a-search#637` in that prompt does not NACK and does not stop the model. Each accepted assign is injected as `@@BOBJOB1|key|directory|FROM ...`. `inject_console` runs that through `one_line`, which turns tabs into spaces, so the separator is a pipe. A line that loses that frame is NACKed and is not started in the worker folder. There is no shared `opencode-project-dir.txt`.
- A drive-root base, a forbidden path, or a `..` / empty repo leaf is NACKed before ACK. A missing directory is created first (FR #6320); only a create failure NACKs `worktree-create-failed:<class>`. Two job ids in one message, or several assigns collapsed by the flood guard, are NACKed `job-context-ambiguous` with no ACK. That is not DONE.
- If the folder disappears after ACK, the launch NACKs that message's key and a later copy of the same assign is judged again. Headless DONE/GIVEUP go to `<worktree>\.bob\outbox.txt` (FR #6333); the worker relays them. This does not grant `external_directory`.
- FR #6333: OpenCode jobs use in-worktree `BOB_OUTBOX` at `<worktree>\.bob\outbox.txt`. Create `.bob\` before launch; exclude via `.git/info/exclude`. Relay forwards only ACK/DONE/NACK/GIVEUP for the assigned job key; program ACK-on-receipt stays on the run-dir outbox and model ACK duplicates are dropped.
- There is no seat-wide `BOB_OPENCODE_DIR`. A stale manual directory is not the project context. There is no `external_directory` allow and no `OPENCODE_CONFIG` grant.

PR #6241 (on main) is the preflight script: relaunch with the job worktree as cwd, or ask for narrow consent. This launch follows that. It does not add a second copy of that script and it does not widen consent.

## Parent handoff

Do not restart or stop OpenCode seat `marchhare-22088` from this note, and do not touch any other seat. No install and no auth change is in this PR.

After review, rebuild `bob-worker.exe` only (`scripts\Build-BobWorker.ps1`). A later OpenCode start, by a person:

1. `gh auth status` must show the CLI logged in. If it says `gh auth login`, a person runs that. Do not open `hosts.yml` or `C:\passwords`.
2. On assign the worker creates `Get-BobiverseJobWorktreePath` when missing (FR #6320). With no base env that is `<data-drive>\ai\worktrees\<repo>\<fr-N>`. Creation is idempotent (`git worktree add` from the machine clone / install root for bobiverse). A create failure NACKs `worktree-create-failed:<class>` before ACK. Credential paths stay refused.
3. Confirm a child `opencode run` for that job folder includes `--dir` of that folder and does not include `--auto`. Confirm `$env:BOB_OUTBOX` is `<worktree>\.bob\outbox.txt` and that a DONE written there reaches the shop with no `external_directory` prompt (FR #6333; live MarchHare proof by Slab after hotpatch). Confirm a create failure posts `NACK ... worktree-create-failed:` and does not post ACK or DONE. Confirm a missing `gh auth status` exits with `gh_auth_missing` and does not post DONE.

Windows search inside the seat is `Get-ChildItem` and `Select-String`. If OpenCode prints `auto-rejecting`, do not retry a wider path.

# AGENTS - bob worker folder (<ai root>\bob\worker)

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://bob.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `..\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `..\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `..\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

**Harvest repo (a-search incident 2026-10-08):** always pass the job's repo: `Invoke-BobiverseHarvest.ps1 -Repo <owner/repo of the job> -Summary ... -Lesson ...` (job `FR SimonBarnett/a-search#N` -> `-Repo SimonBarnett/a-search`, which lands in a-search `.grok/skills/harvest-agent-skills/SKILL.md`). Never harvest a-search or other product lessons to SimonBarnett/bobiverse; only Bob fleet tooling lessons use `-Repo SimonBarnett/bobiverse`.

You are a **NEW worker agent** started by `bob-worker.exe` (tray `Agent` click or command line). Fresh session every time: never resume, continue or attach to an older agent, window or conversation.
Your working folder is `<ai root>\bob\worker`. This file is also shipped as `CLAUDE.md`, `GROK.md` and `.cursor/rules/bobiverse-worker.mdc`.

## Read first (in this order)

- `.grok/skills/bobiverse-worker-seat/SKILL.md` - how you receive and answer IRC messages, what you may and must not touch
- `.grok/skills/bobiverse-bob-worker/SKILL.md` - how the worker program starts you, selects the agent, restarts you if hung
- `.grok/skills/bobiverse-bob-job-irc/SKILL.md` - EXACT ACK / DONE / NACK / GIVEUP lines, `!bored`, which channel, when to send each (read before any job)
- `.grok/skills/bobiverse-bob-job-fr/SKILL.md`, `bobiverse-bob-job-mrb`, `bobiverse-bob-job-uat` - one skill per job type, each with its process diagram, evidence and owners
- `.grok/skills/bobiverse-bob/SKILL.md` and `.grok/skills/bobiverse-fleet-ops/SKILL.md` - the bob service and fleet rules
- `.grok/skills/harvest/SKILL.md` and `.grok/skills/harvest-agent-skills/SKILL.md` - harvest + intake

## How you are driven

- IRC messages for this machine's shop channel arrive as typed input: `FROM <nick> <target> <text> … [outbox: <path>]`. Treat each as the task. Answer by appending
  `PRIVMSG #<machine> :<text>` to `$env:BOB_OUTBOX` (FR #2380; fallback: first-instruction path or the `[outbox:]` footer). Never the ear's `home\outbox.txt`. Then end the turn. `ping` is answered for you.
- You speak ONLY in your own `#<machine>` channel. Never message a nick, never join other channels, never use `#bobiverse`.
- If the IRC link drops the worker program ends you - that is by design. If you hang it restarts a NEW agent; the message in flight is re-delivered.

## Hard rules (CAST IRON)

- Hotpatch safely: back up first, change only what the task needs, restart ONLY the one service concerned; never touch Ergo (`<ai root>\ergo`, `ircd.yaml`) or `BobIrcd`, never kill other seats/agents/tray.
- PowerShell only (never wrap in `powershell -Command`). Never print, store or commit secrets (`*.password`, `github.token`, `identity.json`, NickServ/SASL values, API keys).
- Never write realistic secret literals in tests (contiguous JWT / `Bearer`+token / `password=` hunter-style). Runtime-assemble from parts or use `FAKE_` / `EXAMPLE` placeholders (FR #3304; a-search `tests/fixtures/fakeSecrets.js`).
- Do not rebuild, release or bump `VERSION` - EXCEPT in an assigned UAT job that finds NO gaps against the VISION/specs (then: docs/READMEs updated, `VERSION` bumped, release created, per `bobiverse-bob-job-uat`; any gap = an FR each via intake and NO release). Merging happens ONLY inside an assigned MRB job (that PR and its one docs/fix PR) or the docs PR of a gap-free UAT job; a UAT stamp ONLY inside an assigned UAT job; an FR job never merges. Never post `!bored` (the program does) and keep ACK/DONE exactly as `bobiverse-bob-job-irc` says.
- Always finish with the harvest step (rule above): file every issue/FR/bug and every learned playbook.


## Issues close with their PR

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

- Every FR PR body contains `Closes <owner>/<repo>#N` for the originating issue; a successful MRB merges (if authorised) or confirms that link and closes the issue itself with a comment when the merge did not (e.g. non-default branch). FR/MRB DONE only after that is verified (`bobiverse-bob-job-fr` / `-mrb`).

## The repo is the parent folder

Your CWD is `<ai root>\bob\worker`; its parent `<ai root>\bob` is a sparse git work tree (`bob/` + `common/`) fast-forwarded on every ircBob start. **CAST IRON (FR #4843):** never `git checkout` / `switch` / `commit` / `merge` in the install root itself --- that leaves live seats reading an unreviewed `fr-*` branch. Always `git -C <install> worktree add -b fr-N <job-wt> origin/main`, write `.bobiverse-seat`, then `git sparse-checkout disable` once in the job tree; file intake with `..\scripts\Report-BobiverseIntakeIssue.ps1`. Do not edit the flat copies (`..\scripts\`); they are rebuilt from the tracked folders.

**CAST IRON (FR #4988):** resolve `<job-wt>` with `Get-BobiverseJobWorktreePath` (from `Bobiverse-Common.ps1`): default `<data drive>\ai\worktrees\<repo>\<job>` (D: when a data disk exists; system drive only when there is none). Override with env `BOB_JOB_WORKTREE_BASE`, or `BOB_BRIDGE_HOME\worktrees`. Scratch folders use `Get-BobiverseJobScratchPath`. **Never** create a worktree at a drive root (`D:\bobiverse-fr-N`). `Clear-BobiverseJobWorktrees.ps1` cleans under that base and keeps trees with uncommitted or unpushed work.

- **FR #3948 (merge-on-green):** MRB seats never poll/watch CI and never loop merging main in. After review + tests + own pushes: post MRB PASS with the head SHA; if not held, `gh pr merge <n> --auto --merge` when the repo has `allow_auto_merge`, else comment `merge-on-green pending`; never fold just because the PR is behind (FR #4649: fold only when CONFLICTING/DIRTY or CI failed on a main-fixed issue); then DONE at once. Full rules: `.grok/skills/bobiverse-bob-job-mrb/SKILL.md` section "FR #3948".

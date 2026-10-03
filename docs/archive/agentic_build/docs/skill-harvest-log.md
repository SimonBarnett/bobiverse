<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/skill-harvest-log.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Skill harvest log

## 2026-09-23 — cleanup-orphans

Simon: close orphan python/node/powershell after agent/IRC churn.
Harvested `cleanup-orphans` + `tools/Cleanup-OrphanAgents.ps1`. Keeps
newest fleet watchers, tray, bob-*, Jeeves, live session; kills stale
irc_listen/TSR, duplicate Watch-*, old cursor-agent, bare powershell.
Related: `killproc` (named hung seat), `bob-fleet-tray` (tray recycle).

## 2026-09-23 — land quiet-talk park doc (#36 FIX)

Simon: bare `pip install aider-chat` on MarchHare hit `WinError 5` on
`_cffi_backend*.pyd` (locked by bob-marchhare / other Python), then `aider`
not on PATH. Preferred install is a dedicated user venv + User PATH; document
temp-dir warnings and free-model env. Home: `setup-bob-aider`. Fuel id
`aider-free`.

## 2026-09-23 (mojibake) land quiet-talk park doc (#36 FIX)

Land `docs/feature-request-bobiverse-quiet-talk-2026-09-20.md` on main after CONFLICTING PR #35. Keep live `bobiverse.md` / `bob-irc` channel-talk + digest `!bobiverse` law. Supersession note on the park file â†’ #74 / agentic_irc#6. No implementation in this FIX.

## 2026-09-23 (mojibake) preferred IRC wake = Watch-AgentHealth

Simon: do not arm in-session `listen.stdout.log` `^FROM ` TSR (burns
tokens on `#bobiverse` spam). Preferred: Watch-AgentHealth /
AgentMonitor forwards FROM. Harvested `watch-agent-health` into this
repo; updated `agent-monitor-setup`, `bob-irc` stub. Sister
`agentic_irc` skills `agentic-irc` + `bob-irc` Listener + wake CAST IRON.

## 2026-09-23 (mojibake) intake must run validate-vision-pack

skills-visionary #6 / PR #7 (`2c98dfd`) shipped
`tools/validate-vision-pack.py`. `bob-spec-intake` and `visionary` now
refuse park/dispatch unless that command exits 0 (product `tools/` else
sister clone). Home: `bob-spec-intake`, `visionary`.

## 2026-09-23 (mojibake) visionary at new-product intake

Simon: high-reasoning skill for the long-term strategy of a new product
(measurable success, service/website/app, stack, architecture, HTML
mocks). Required before park/dispatch. Feature requests skip it. Homes:
`visionary`, `docs/templates/vision.md`, `bob-spec-intake` New product
step 0.

## 2026-09-23 (mojibake) bob-spec-intake: Grant script opens settings/installations

`bob-spec-intake` New GitHub repo step 3: `Grant-CursorGitHubApp.ps1` opens
Configure existing at https://github.com/settings/installations, not
`/apps/cursor/installations/new`. Home: `bob-spec-intake`.

## 2026-09-23 (mojibake) All repos already set: disconnect/reconnect, then local gh

Simon: Cursor GitHub App already has All repositories plus the full
permission list (code + pull requests write). receive-pack still
denied to cursor[bot]. That is a stale/stripped Cursor installation
token, not another GitHub click. Disconnect+Connect at
cursor.com/dashboard/integrations as SimonBarnett. If still 403,
use local gh / fleet cursor-agent. Home: `setup-github-cursor`.

## 2026-09-23 (mojibake) Cursor app permission list is enough; 403 is repo access

Simon pasted the Cursor GitHub App permissions: Read on administration,
commit statuses, deployments, metadata, packages, pages; Read and write
on actions, checks, code, discussions, issues, merge queues, pull
requests, workflows. That is the correct grant (`code` = Contents).
A receive-pack 403 with that list is Repository access (All vs
Selected), not missing scopes. Home: `setup-github-cursor`.

## 2026-09-23 (mojibake) Configure existing Cursor install; do not /installations/new

Simon: Cursor Web still 403 on PRs after the grant pages. `cursor[bot]`
receive-pack is the pusher; `cursoragent` is only the git author
(`cursor/*` on agentic_build worked 2026-09-20).
`/apps/cursor/installations/new` can replace a Selected-repos list and
drop agentic_build. Use https://github.com/settings/installations
Configure -> All repositories, then dashboard Integrations reconnect.
Do not add cursoragent as a collaborator. Home: `setup-github-cursor`.

## 2026-09-23 (mojibake) cursor[bot] is not a collaborator; gh cannot prove the grant

Simon: try-now after the Cursor app page. A TUI `gh` seat cannot replay
`git-receive-pack` as `cursor[bot]`. `PUT collaborators/cursor[bot]` is
404 (not a user). `GET collaborators/cursor[bot]/permission` is `none`
on every repo (apps are not collaborators). `user/installations` is 403
on a classic user token. Real test is Cursor Web push. Pages:
`apps/cursor/installations/new?target_id=2916380`,
`settings/installations`, `cursor.com/dashboard/integrations`. Home:
`setup-github-cursor` + `tools/Grant-CursorGitHubApp.ps1`.

## 2026-09-23 (mojibake) Cursor GitHub App on every git (All repositories)

Simon: Cursor Web 403 on PRs was `cursor[bot]` denied
`git-receive-pack` on agentic_build. Public repos already allow human
fork PRs. Fix is the Cursor GitHub App = **All repositories** (Contents
+ Pull requests write). User `gh` cannot grant an app install. New repo
checklist: public + webhook + this app. Homes: `setup-github-cursor`,
`bob-spec-intake` New GitHub repo, `tools/Grant-CursorGitHubApp.ps1`.

## 2026-09-23 (mojibake) leftover FAIL after another worker merged

AgentMonitor #22: MRB of `7d49dd0` posted PASS-nits, then `gh pr merge`
failed because the PR head moved. Worker voided and opened FAIL. A
second seat had already merged the later head. Leftover FAIL must
close with the merged PR URL; do not FIX a MERGED PR. Home:
`bob-hostile-mrb`.

## 2026-09-23 (mojibake) new repo is public PRs plus the git webhook

Simon: creating a new repo must leave it public so anyone can open a
PR, and must add the GitHub hook in the same turn. Home:
`bob-spec-intake` section **New GitHub repo**. Hook playbook stays
`setup-github-webhooks` (`https://irc.ntsa.uk/bob/v1/git`, events
push / pull_request / issues, no secret).

## 2026-09-23 (mojibake) split setup-github-webhooks + setup-ssl-certs

Simon: one skill that shows how to set up webhooks on git, one on
setting up SSL certs. Homes: `setup-github-webhooks` (gh hook JSON,
all repos, 204) and `setup-ssl-certs` (win-acme IIS, do not touch
Ergo PEM). `github-irc-webhooks` is a pointer only.

## 2026-09-23 (mojibake) GitHub webhooks + IIS HTTPS on irc.ntsa.uk

Ionos IIS `irc-ntsa` has Let's Encrypt (win-acme renewal
`IIS irc-ntsa webhook`). Default GitHub hook on every SimonBarnett
repo: `https://irc.ntsa.uk/bob/v1/git` (push/PR/issues). Fleet
`reportUrl` is `https://irc.ntsa.uk/bob/v1/report`. New repos need
the hook added (no user-account default). Do not replace the Ergo
PEM renewal. Home: `github-irc-webhooks`. Jeeves announce stays
agentic_irc `jeeves-git-webhook`.

## 2026-09-23 (mojibake) harvest as a PR, not main

Simon `#bobiverse`: update builder skills (mojibake) send skills harvest as a
PR, NOT a commit to main. Home: `harvest-agent-skills` +
`Harvest-AgentSkills.ps1`.

## 2026-09-23 (mojibake) FR you parked is a bob job

Simon `#bobiverse`: `Standing rule if you get a FR, you bob job it`.
Park (`bob-spec-intake`) then `bob-job-loop` unless he said park-only.
Homes: `bob-spec-intake` + `bob-job-loop`.

## 2026-09-22 (mojibake) PASS-nits merge-in-progress + no gh `merged` field

`gh pr view --json state,merged` fails (unknown field `merged`).
`Test-BobGhPrIsMerged` then always returned false, so PASS-nits finish
retried `gh pr merge` and died on `GraphQL: Merge already in progress`
without closing boards (agentic_irc #135 / PR #145). Query
`state,mergedAt`. If merge stderr is in-progress but `state` is MERGED,
treat merged and close. Home: `bob-job-loop` + `tools/Bob-BuildLoop.ps1`.

## 2026-09-22 (mojibake) talk seats own bob jobs

Simon `#bobiverse`: `no - the bob jobs are YOURS`. Idle talk seats run
`bob-job-loop` on unowned open issues. Do not leave the queue to
`bob-*` / Watch. Home: `bob-job-loop`.

## 2026-09-22 (mojibake) bob-job checks open issues as well as FRs

Simon `#bobiverse`: bob-job must scan **all open issues** (and open PRs),
not only `--label feature-request`. Skip pure MRB meta boards. Unlabeled
/ other-label open issues are work (intake then loop). Homes:
`bob-job-loop` + `bob-hostile-mrb`.

## 2026-09-22 (mojibake) CAST IRON: harvest back to the relevant repo

Simon `#bobiverse`: every skill repo has a harvest skill as foundation
(like `harvest-agent-skills` here). If you learn something new, harvest
it back to the **relevant** repo immediately. `harvest-agent-skills` +
`bob-spec-intake` (new skill packs LOCK a harvest skill in P0).

## 2026-09-22 (mojibake) gh pr merge must pass --merge (non-interactive)

ehf #5 PASS-nits finish FAILED: `gh pr merge` without `--merge`/`--rebase`/`--squash` when not a TTY. PR #10 was MERGED a moment later; treat DONE. Driver `Invoke-BobGhMergePrIfOpen` now passes `--merge`.

## 2026-09-22 (mojibake) MRB no-Bob: find next seat, do not sit

Simon `#bobiverse`: if you MRB and there is no Bob but open issues
remain, find someone to take the next dev (mojibake) do not let it sit. Add to
skills and harvest. `bob-hostile-mrb` + `bob-job-loop`.

## 2026-09-22 (mojibake) MRB MUST close, merge, and pull completed PRs

Simon `#bobiverse`: VERY important. After PASS-nits, MRB must close
finished issues, merge the pull request, and pull completed PRs so the
next job is not on stale main. `bob-hostile-mrb` + `bob-job-loop`.
Detailed FRs are also meant to be done at MRB (not park-only).

## 2026-09-22 (mojibake) harvest before dismiss + PASS-nits merge race

Simon `#bobiverse`: Bob must remind workers to harvest skills before
dismissing them. `harvest-agent-skills` + `bob-job-loop` On wakeup.
`FAILED: PASS-nits finish: PR still open after gh pr merge` is a race:
if the PR is MERGED and the FR is CLOSED / PASS-nits, treat DONE; do
not relaunch a build (marchhare irc-skill #1).

## 2026-09-22 (mojibake) Watch must not enqueue !bobiverse (Simon go-for-it)

Simon on #bobiverse: go for it. `!bobiverse` answer is Jeeves-only.
`Request-BobIrcBobiversePull` no longer enqueues channel `!bobiverse`
unless `BOB_IRC_ENQUEUE_BOBIVERSE_PULL=1`. Talk seats never answer it.

## 2026-09-23 (mojibake) bob-* must call !bobiverse again (#196)

Simon #bobiverse / issue #196: each `bob-<machine>` on `Watch-Bobiverse`
enqueues `!bobiverse` on the ~120s cadence again. `Test-BobIrcBobiversePullSeat`
blocks talk seats (`{machine}-{pid}`) and shop `w-*` workers. After chair
digest ingest, `Sync-BobDigestWebhookAfterBobiversePull` POSTs only when local
fuel/jobs/online differs from the chair digest machine row (`_chair-digest-peers.json`;
#141 change-only).

## 2026-09-22 (mojibake) fleet harvest irc skill + failed-pong restart

Simon `#bobiverse`: `everyone harvest your irc skill`; live seat on a
box restarts a nick that fails to pong. Triggers added to
`harvest-agent-skills` and `killproc`. IRC body lives in `agentic_irc`.

## 2026-09-22 (mojibake) killproc -Roll shop channel from nick

Marchhare-20280: killproc -Roll joined #flamingo on marchhare-23624.
`Stop-HungAgent` now sets `--channel #bobiverse,#<machine>` from the
nick (marchhare-23624 -> #marchhare). Do not hardcode #flamingo.

## 2026-09-22 (mojibake) killproc: -IrcHome, working seat, new cursor-agent

Simon: harvest the second-seat night. Param is `-IrcHome` (never `-Home`;
`$Home` is read-only). Working live seat killproc-rolls the hung *other*
home only; missing cursor-2 means no hung seat. `-Roll` is still deaf
until a Cursor TSR. After close: new `cursor-agent.ps1` with prompt file
(`--trust --force --model grok-4.6`); no `cmd.exe /c` prompt; no Halloy
SendKeys. Skill `killproc`. Talk-seat nick/home stay `agentic-irc`.

## 2026-09-22 (mojibake) killproc (end hung agents)

Simon: create a new killproc skill to end hung (jung) agents.
`Stop-HungAgent.ps1 -IrcHome <seat> -Nick <nick> -Roll` kills only
`irc_agent`/`irc_listen` on that home, then rolls a replacement.
Do not spray Stop-Process. Named Grok Bot remains `unstick-grok-bot`.
Skill `killproc`.

## 2026-09-21 — IRC TSR: Start-IrcTsr.ps1 + Watch-CursorIrc

`tools/Start-IrcTsr.ps1`, `_Start-IrcTsr-ionos.ps1`; wake
`^AGENT_LOOP_WAKE_irc-tsr`; `Watch-CursorIrc` starts TSR not bare listen.
Skills `agentic-irc`, `bob-irc`.

## 2026-09-25 — IRC TSR: coordinator.pid nick drift (PR #334)

flamingo: talk-seat key=value `coordinator.pid` broke per-script `[int]` parse →
Start/Watch nick mismatch → Start-IrcTsr every 30s (pre-#326: 1833 orphan listens).
`tools/Irc-Tsr-Coordinator.ps1` shared parser + respawn backoff; test
`tests/BT0irtsr-coordinator-nick.ps1`. Do not touch flamingo from implementer seats.

## 2026-09-21 — IRC: ALWAYS listen + Watch-CursorIrc

`agentic-irc` / `bob-irc`: `irc_listen.py` must stay up on fleet Cursor seats
(`cursor-<machine-id>`, `~/.agentic-irc-cursor`). `tools/Watch-CursorIrc.ps1`,
`_Watch-CursorIrc-ionos.ps1`. Still MUST reply via outbox same turn.

## 2026-09-21 — FR queue: receive order until PASS-nits

One FR at a time per repo: user-stated sequence or lowest open
`feature-request` #; do not start the next loop until the current board is
`phase=pass` (MRB PASS-nits). Replaces “fan out all open FRs after DONE”.
Skills: `bob-job-loop`, `bob-build-loop`, `bob-hostile-mrb`, `cursor-mrb-dev`.

## 2026-09-21 — GitHub hygiene scripts + PASS-nits merge gate

`Start-BobMrb.ps1` requires `-PrUrl`; merges with `gh pr merge --merge`
before posting PASS-nits. Operator: `Close-BobMrbPassedIssues.ps1`,
`Close-BobSupersededGithub.ps1`, `Merge-BobMrbPassOpenPrs.ps1`. Skills:
`bob-job-loop`, `bob-hostile-mrb`, `bob-build-loop`.

## 2026-09-21 — MRB: re-read mergeable immediately before PASS-nits

`bob-hostile-mrb`: GitHub `CLEAN` can flip to `CONFLICTING` while the
board is written (main moved). Re-query `mergeable` immediately before
posting PASS-nits. If `gh pr merge` then fails, void that pass board and
open a new FAIL issue on the same SHA. Learned on open-tts PR #87 /
SHA `86cabf9` (issues #134 then #135).

## 2026-09-21 (mojibake) MRB worker: isolate review SHA; CONFLICTING is FAIL

`bob-hostile-mrb` worker steps: if the shared checkout HEAD is another
job, use a detached worktree at the review SHA (do not reset that
branch). A GitHub `CONFLICTING` PR is FAIL even when acceptance is
green in isolation (mojibake) PASS-nits includes merge.

## 2026-09-21 (mojibake) bob-job launchers + MRB remaining-FR rule

Harvest from live bob-job loops:

- `tools/run-bob-build-loop.ps1` and `tools/start-bob-build-loop-issue.ps1`:
  GCM / credential-manager for `GH_TOKEN` (do not rely on interactive
  `git credential fill` when `gh` is the helper).
- `bob-job-loop`: unique LogPath, recover missed PR; after DONE start **next**
  queued FR only (see 2026-09-21 FR queue harvest).
- **MRB rule:** new worker on MRB FAIL (FIX). After PASS-nits, **one** next FR
  in receive order — not parallel FR loops. Homes: `bob-hostile-mrb`,
  `bob-job-loop`, `bob-build-loop`, `cursor-mrb-dev`.
- FIX #112: `ConvertFrom-BobGhJsonList` keeps issue `body`; restore `-Pr`
  to `Start-BobMrbHandoff`; Test-Pack BT0loop10/11. Audit write must not
  abort DONE.
## 2026-09-21 Ã¢â‚¬(mojibake) running Bob jobs (dispatcher playbook)

Fleet runs of `bob-job-loop` across agentic_build / agentic_irc / open-tts.
Promote: `tools/run-bob-build-loop.ps1` (credential-manager GH_TOKEN first),
unique LogPath, isolated worktree per FR, pin existing PRs with `-Sha`/`-Pr`,
FIX PR titles match `priorMrbIssue`, gh JSON unzip, `$PID` not overwritten,
cursor-agent status stderr non-fatal, Add-Content log lock fallback.
`bob-job-loop` skill owns the dispatcher hard rules. Driver files:
`Start-BobBuildLoop.ps1`, `Bob-BuildLoop.ps1`, `Start-BobCursor.ps1`.

## 2026-09-20 Ã¢â‚¬(mojibake) build/MRB loop driver (notify on PASS-nits)

`bob-job-loop` / `tools/Start-BobBuildLoop.ps1`: dispatcher launches one
program; stdout `DONE` on MRB PASS-nits. Starts the PR worker, hands MRB
to a different `-Kind mrb` agent, retries failed cursor/grok jobs (max 3
attempts per phase), reads Required fixes on FAIL, back-links boards.
State under `$BOB_BRIDGE_HOME/loops`. Does not stamp UAT. FR:
`docs/feature-request-mrb-loop-automation-2026-09-20.md`.

## 2026-09-20 Ã¢â‚¬(mojibake) dispatcher hands every worker PR to a different MRB worker

When a worker opens a PR, the dispatcher immediately `Start-BobMrbHandoff`
(`-Kind mrb`, new job, isolated worktree). Never the implementer. Never
resume the Composer session. FAIL still spawns a FIX worker who opens a
new PR; that PR is MRBd by yet another worker. Home: `bob-build-loop`.
Pointers: `cursor-mrb-dev`, `bob-hostile-mrb`.

## 2026-09-20 Ã¢â‚¬(mojibake) PR/MRB transaction: Cursor Models then grok

Simon: Cursor Models (Cursor Grok + Composer) for MRBs and PRs until that
pool is empty, then grok.exe. Never Other Models. Tray/capacity must show
Cursor Models remaining % (20 Sep Spending: 1% used; tray had labelled
Sand overage as Cursor Models). Both MRB and implementation are handed off.
Workers open PRs. PASS-nits: MRB agent merges. Every FAIL: spawn a FIX
worker. Table + mermaid in `bob-build-loop` / README. `models.mrbCursor`
is Cursor Grok `grok-4.6`, not `claude-opus-5-thinking-high`. FR:
`docs/feature-request-pr-mrb-cursor-models-transaction-2026-09-20.md`.

## 2026-09-20 Ã¢â‚¬(mojibake) customer paid their bill

Standalone `cursor-sand-billing`: Grok Bot deaf Ã¢â€ (mojibake) Sand 100% / Stripe `NEEDS_AUTH` / Open invoices at `cursor.com/dashboard/billing` (not Spending). After Paid, one ping. Do not Recreate. `box-usage` still owns the numbers.

## 2026-09-20 Ã¢â‚¬(mojibake) Cursor MRB/FIX until PASS-nits

`cursor-mrb-dev`: hand off Cursor MRB (reasoning model) then Cursor
builder (`composer-2.5`) until a new `MRB FAIL|PASS-nits` issue on the
new SHA. `start-bob-cursor` owns login, `-Kind`, in-process `-Goal`,
`--` before prompt, Win32_Process.Create, no RedirectStandardOutput.
`bob-hostile-mrb`: new MRB issue per SHA; do not reuse the old FAIL as
the board. `bob-build-loop` points here; fuel is Cursor then Grok.

## 2026-09-20 Ã¢â‚¬(mojibake) bob-irc canonical in agentic_irc

All IRC playbooks (client, SEAL, moot, file, dumb, invite-airc, Ergo
start/firewall, Watch-Bobiverse recycle, Halloy) live in
`https://github.com/SimonBarnett/agentic_irc` `.grok/skills/`. This repo
keeps a `bob-irc` stub (Test-Pack / Install-BobFleet) plus
`config/bobiverse.json` and `docs/bobiverse*.md`. `harvest-agent-skills`
routes IRC harvests to agentic_irc.

## 2026-09-20 Ã¢â‚¬(mojibake) unpaid Open Cursor invoices silence Grok Bot

Cursor dashboard: "You may have an unpaid invoice" plus invoice Status Open (20 Sep mid-month cycle starting 16 Sep; 16 Sep cycle starting 14 Sep). Same as Stripe `NEEDS_AUTH` + Sand 100%. Pay Open rows, then one Bob ping. `box-usage`.

## 2026-09-20 Ã¢â‚¬(mojibake) Stripe Link NEEDS_AUTH blocks Sand on-demand

`ListGrokBotStripeLinkPaymentMethods` returned `GROK_BOT_STRIPE_LINK_PAYMENT_METHODS_OUTCOME_NEEDS_AUTH` while `GetSandUsageStatus` was 100% with on-demand enabled. Box send 503. Human must finish payment method in Grok Bot Settings > Usage. `box-usage` + `unstick-grok-bot` step 3.

## 2026-09-20 Ã¢â‚¬(mojibake) Sand usagePercent 100 silences Grok Bot

Dashboard `GetSandUsageStatus` `usagePercent: 100` (reset `nextResetTimestampUtc`). Turns `ACCEPTED_TEMPORAL` with no `send-message` and no limit banner. On-demand enabled / `hasAvailableUsage: true` still silent; box harness 503. Check this **before** RecreateSandBox. `box-usage` owns the Sand numbers; `unstick-grok-bot` step 3 points here.

## 2026-09-20 Ã¢â‚¬(mojibake) cursor-agent prompt must not look like CLI flags

Node `cursor-agent` treats unquoted prompt tokens as options
(`unknown option '-join'`). Launch with `--` before the prompt, and do
not put PowerShell `-join` or raw double-quotes in the goal string.

## 2026-09-20 Ã¢â‚¬(mojibake) Start-BobCursor must leave the grok Job Object

`Start-Process` children are killed when the grok.exe shell that called
`Start-BobCursor.ps1` exits. Use `Win32_Process.Create` so cursor-agent
outlives the dispatcher. Combined with no `RedirectStandardOutput` on
the parent (PS 5.1 wait bug).

## 2026-09-20 Ã¢â‚¬(mojibake) Start-BobCursor must not wait on the agent

`Start-Process -RedirectStandardOutput -PassThru` in Windows PowerShell
5.1 still waited for cursor-agent (handoff `ConvertTo-Json` returned
after 843s when pid 11464 exited). Redirect inside `launch.ps1` instead;
parent Start-Process is Hidden + PassThru only.

## 2026-09-20 Ã¢â‚¬(mojibake) cursor-agent prompt via launch.ps1

`Start-Process -ArgumentList` mangles a multiline MRB prompt (quotes
split the node argv). Write `cursor-agent-<job>.prompt.txt` and a
`launch.ps1` that reads it and passes one argument to `cursor-agent.ps1`.
Skip empty Docs/Plan so the prompt is not `Read  and .`.

## 2026-09-20 Ã¢â‚¬(mojibake) grok.exe has no build0.1; resolve equivalent

`grok models` on 1.0.34 is only `grok-4.6` / `grok-4.5` (`-m build0.1` is
unknown model id). Keep `models.buildGrok=build0.1`. `Resolve-BobGrokCliModel`
maps it to `models.buildGrokFallback` (`grok-4.5`) before `grok.exe -m`.
When the catalog lists `build0.1`, the preferred id is used as-is.
Cursor builders stay `composer-2.5`; MRB stays `grok-4.6` /
`claude-opus-5-thinking-high`. `-m grok-4.6` already bills `grok-4.6-build`.

## 2026-09-20 Ã¢â‚¬(mojibake) MRB reasoning vs build0.1

MRB jobs use the latest reasoning model (`models.mrbCursor` /
`models.mrbGrok`). Build workers use `build0.1` or Cursor `composer-2.5`.
`Get-BobJobModel`; grok.exe `-m`; cursor-agent `--model`.

## 2026-09-20 Ã¢â‚¬(mojibake) MRB fuel is Cursor then Grok

`Start-BobMrbHandoff` / picker default: `cursor-models` then `grok-build`. Copilot only with `-AllowCopilot`. `Start-BobCursor` must not launch `~\.grok\bin\agent.exe` (that is grok.exe).

## 2026-09-20 Ã¢â‚¬(mojibake) Bob hands off MRBs

Bob does not write the hostile review in-session. `tools/Start-BobMrbHandoff.ps1` posts `@copilot` on the feature-request issue (CCA if enabled) or `-Fleet` git-task. Worker: FAIL / PASS-nits only. Only Bob stamps ready for human UAT. Missing-features check stays in `bob-hostile-mrb`.

## 2026-09-20 Ã¢â‚¬(mojibake) MRB requests missing features

`bob-hostile-mrb`: every board walks this FR's acceptance **and** holes with no parked request. Red acceptance stays Required fixes. Unspecified holes / issues with no intake doc are **requested** (`bob-spec-intake` issue + `docs/feature-request-*.md`), not implemented in the MRB job. Body section **Missing features**.


## 2026-09-20 Ã¢â‚¬(mojibake) PRs #5 and #6 not merged (stale drafts)

Checked both open drafts vs `main`. Merging either would rewind later tray/git-task work (PR #5) or restore hover/iconProbe/hideTip (PR #6, issue #3). Pulled the unique bits that `main` lacked: per-machine `_Watch-Bobiverse-*.ps1` wrappers (kept ionos env-specific wrapper) and the native P+ idle chip screenshot. Closed the PRs as superseded.

## 2026-09-20 Ã¢â‚¬(mojibake) action GitHub issues #1 #3 #4 #7 #8

- `setup-remote-grok-bot`: flamingo remote CLI+desktop playbook (Mode 3 put+spawn, no-GPU, window-state 0x0). Temporal hangs stay `unstick-grok-bot`.
- `reinstall-agentic-build-skills` + `tools/Reinstall-AgentSkills.ps1`: copy `.grok/skills` to `~/.grok/skills`; optional single-instance tray recycle (issue #3).
- `start-bob-cursor` + `Select-BobGitWorker` / `Get-BobCapacity`: git-task dispatch is `(machine, fuel)`. Cursor Models is the shared top bar, not a machine named cursor. DUMB/2012 is not a git worker.
- Tray issue #3: do not merge PR #5 (it would drop seat labels / GBP overage). BT0n now asserts click-only / no hover; `Install-BobFleet` registers `_Watch-Bobiverse-<id>` without double-starting an already-running moot.

## 2026-09-20 Ã¢â‚¬(mojibake) unstick: new Temporal agent also hung

Created throwaway `Builder` (`CreateGrokBotTemporalAgent`). Its `grok-bot-turn-<newId>` ACCEPTED a PONG with no send-message, same as Bob and Haitch. `SendGrokBotUserMessage isFork` still returns Bob's old workflow id. Stop Recreate.

## 2026-09-20 Ã¢â‚¬(mojibake) unstick: account-wide Temporal

If Haitch (or any idle agent) also ACCEPTED_TEMPORAL with no send-message, RecreateSandBox cannot fix it. Probe a second agent before more Recreate. `window-state.json` x/y ~-32000 w/h 0 is a separate Electron blank; kill, rewrite bounds, relaunch `--disable-gpu`.

## 2026-09-20 Ã¢â‚¬(mojibake) unstick wait for new podId

RecreateSandBox `started: true` is not success. Poll EnsureSandBox until `podId` changes (1-3 min; API can timeout mid-transfer). Two 30s samples of the **old** id mean the box has not rotated.

## 2026-09-20 Ã¢â‚¬(mojibake) harvest during the job

`harvest-agent-skills` now fires in-session: if a build/fleet job learns a repeatable procedure, write the skill, log, commit, push `origin/main`. Hourly `BobSkillHarvest-*` is backup. `grok-build-fleet` points here.

## 2026-09-20 Ã¢â‚¬(mojibake) unstick: shared sandbox + Waiting to send

- Recreate once per shared Grok Bot sandbox, not per agent. Wait for transfer toast / stable `podId` before any ping.
- UI **Waiting to send** = PENDING. Preferred recovery ping is the Grok Bot UI. `GrokBotApi.py --wait` looks for a new assistant `send-message` in the transcript, not roster `lastActivityAt`.

## 2026-09-20 Ã¢â‚¬(mojibake) private Ergo + unstick agentId (ionos)

- New skill `bob-irc`: fleet `#bobiverse` is Ergo `irc.ntsa.uk:6697`, not Libera. Join/recycle Watch-Bobiverse only; connect file path not value. Docs remain `docs/bobiverse.md` / `docs/bobiverse-ionos-ircd.md`.
- `grok-build-fleet` Bobiverse section points at Ergo + `bob-irc`.
- `unstick-grok-bot`: RecreateSandBox must pass `--agent` (agentId); ACCEPTED user echo with no later `send-message` is a hung turn.

## 2026-09-20

MRB is a GitHub issue (`Start-BobMrb.ps1`, skill `bob-hostile-mrb`). No MRB PDFs. Feature-request issue + `/docs` markdown is the source of truth.

## 2026-09-20 (copilot)

Harvested `start-bob-copilot`: Grok starts GitHub Copilot cloud agent via `tools/Start-BobCopilot.ps1` (`gh api` user token). Fleet prompt passes that skill so a build `grok.exe` offloads GitHub repo work instead of burning Cursor weekly usage.

## 2026-09-20 Ã¢â‚¬(mojibake) bob-fleet-tray diagnostics harvest (ionos)

Promoted live tray diagnostics into `.grok/skills/bob-fleet-tray/SKILL.md`:
click-only TipForm (no hover), blank NotifyIcon.Text, `#Bobiverse (machine)`
title, seat deals beside names (`config/bob-seats.json`), shared weekly % for
ntsa (marchhare + ce-priority-dev1), cursor overage as red negative pounds from
`tip_cursor.json`, Suspend/Resume redraw to stop poll flash, single-instance
mutex + Restart watcher kill-all. Trigger: recycle Watch-BobTray only after
card/hover changes.

## 2026-09-20 Ã¢â‚¬(mojibake) bob-fleet-tray blank-card + real GBP overage (ionos UAT)

- Dropped WM_SETREDRAW from Suspend/Resume-BobTrayPaint (SuspendLayout only).
- Rebuild-BobTrayTiles formats cursor/seat labels before Controls.Clear.
- Inline overage-red check (no Test-BobCursorOverageLabel from tray).
- Get-CursorAgentUsage.py: spendLimitUsage.individualUsed Ã¢â€ (mojibake) GBP via er-api.
- Skill rewritten with diagnose steps for blank card + no-dialog compile fail.


## 2026-09-20 Ã¢â‚¬(mojibake) ionos Ergo outbox POINT flood

`Write-BobIrcStatus` appending a POINT every Watch tick filled
`~\.agentic-irc-bobiverse\outbox.txt` (~1831 lines). `irc_agent.py` drain
plus Ergo flood limits reconnect-looped `bob-ionos`. Playbook:
dedupe last outbox POINT after stripping `lastSeen=`; compact POINT-only
backlog over 32KB on Start/Install; treat `127.0.0.1` as private Ergo
(not stale/Libera); do not default ionos to loopback without SNI.
Owner: `docs/bobiverse.md` + `bob-irc` stub.

## 2026-09-20 Ã¢â‚¬(mojibake) cursor/xAI remaining + reset dates

- Harvested into `box-usage` and `bob-fleet-tray`: Get-BobWeeklyRemaining / Get-BobCursorAgentWeeklyRemaining / Format-BobResetLabel / IRC reset= / TipForm headings.
- Import-BobIrcPeerTranscript keeps prior period_end when POINT lacks reset=.

## 2026-09-23 -- tray Agents menu + agent-monitor-setup

- New skill `agent-monitor-setup`: the two watch-seat agents (Cursor, Grok)
  collapse into one tray context-menu item **Agents**; select which to launch.
- Each entry's icon is `Icon.ExtractAssociatedIcon` of the agent app exe, so it
  matches the AgentMonitor Desktop shortcut (`shortcuts/*.lnk` IconLocation),
  not the tray robot glyph.
- Not installed -> greyed icon (`ConvertTo-BobTrayGrayImage`), click initialises
  setup via new `tools/Install-AgentMonitor.ps1` (clones AgentMonitor into
  `Desktop\Watch-AgentHealth`, copies its watch-seat skills into `~\.grok\skills`).
- Setup ships with the skill harvest (Copy-BobProjectSkills / Install-BobFleet);
  `harvest-agent-skills` now points at it. Watch-seat runtime contract stays in
  the AgentMonitor repo (`agent-monitor`, `watch-seat`).
- Test-Pack BT0 skills + BT0l traySrc assert the Agents menu, icon parity, grey
  state, and the setup tool. Rule (Simon 2026-09-23): harvest opens a PR, not a
  commit to main.

## 2026-09-24 -- honesty box foundation (harvest-agent-skills)

Replaced `.grok/skills/harvest-agent-skills/SKILL.md` with the CAST IRON
honesty box. Frontmatter `github:` is
`https://github.com/SimonBarnett/agentic_build`. Report order stays PR, else
a `harvest:` / `FR:` issue; never push harvest to main. Short addenda keep
`tools/Harvest-AgentSkills.ps1`, `tools/Install-SkillHarvest.ps1`, the
Test-Pack BT0 list, no product dispatch (`grok-build-fleet` /
`bob-build-dispatch`), and skip `tools/_Watch-*.ps1`. One-line foundation
pointer on `bob-irc` and `visionary` only.



## 2026-09-25 — FR #343 no self-merge FR PRs

docs/fr-mode-no-self-merge.md; tools/fr_self_merge_guard.py; packs FR mode open-PR-only.


## 2026-09-29 — wix-msi-pack (airc-console MSI #309)

- New skill `.grok/skills/wix-msi-pack`: WiX v3 heat/candle/light pack shape, deferred `CAQuietExec64` must use CustomActionData (property = deferred CA id), not `QtExecCmdLine` (msiexec 1603 / 0x80070057).
- Reference: agentic_irc `Pack-AircConsoleRelease.ps1` / `Fetch-Wix.ps1` / `Product.wxs`; product behaviour stays in agentic_irc `airc-console`.
- Harvest-agent-skills domain table + Test-Pack BT0 skills list updated.
- Evidence: CE-PRIORITY-DEV1 install of `airc-console-v0.1.16`; agentic_irc issue #309 / PR #310.

## 2026-09-29 - BOB_MACHINE_ID = COMPUTERNAME (not ionos alias)

- Simon CAST IRON: Install-BobFleet `-MachineId` / `BOB_MACHINE_ID` = Windows `COMPUTERNAME` lowercased.
- Host `WIN-MPRE8VI4U6U` -> `win-mpre8vi4u6u` / `bob-win-mpre8vi4u6u` / `#win-mpre8vi4u6u`. Do not install as `ionos`.
- Skills: `.grok/skills/bob-irc`; comment on `tools/Install-BobFleet.ps1`.
- Do not commit per-machine `tools/_Watch-Bobiverse-*.ps1` wrappers (Install-BobFleet generated).
- Sister IRC playbook harvested to `SimonBarnett/agentic_irc`.


# bob-worker.exe - the tray Agent / Plan items (t762u - t772u)

One compiled program, `<ai root>\bob\worker\bob-worker.exe` (`scripts/bob_worker.py`, built by `scripts/Build-BobWorker.ps1` with PyInstaller, 11 MB, built into the bob MSI by
`Pack-BobiverseRelease.ps1`), starts ONE agent and - in agent mode - owns the IRC connection. Skills text for agents: `.grok/skills/bobiverse-bob-worker`, `-plan`, `-job-irc`, `-job-fr`, `-job-mrb`, `-job-uat`.

## Rules (all enforced in code and tests)

* **Tray**: `Agent` and `Plan` are plain single-click items (no submenu). Each click starts `bob-worker.exe --mode agent|plan --install-root <root> --machine-id <id>` (a per-user run copy under `%LOCALAPPDATA%\Bobiverse\worker\bin`, so the installed exe is never locked by a seat).
* **ALWAYS a NEW agent** (t765u): new session id every time; `--resume/--continue/-r/-c/--session/--chat` are refused (`assert_fresh`); a click never attaches to an existing agent/window/process.
* **ONE window** (t771u): the exe's visible console IS the agent's window. The agent inherits that console (no `CREATE_NEW_CONSOLE`), IRC relay / `!bored` / health run as threads of the same exe. Ending the exe ends the agent (close handler + kill-on-close job object);
  the agent exiting ends the exe. The Grok key prompt (no tokens left) is inside the same console, input hidden.
* **Agent selection is automatic** by tokens: Cursor high or low pool > 0 -> `agent.cmd`; else local Grok weekly > 0 -> `agent.exe`; else a key prompt (memory only). Readings: `tools/Get-BobAgentFuel.ps1`; unknown = not available.
* **CWD** `<ai root>\bob\worker` (agent) / `<ai root>\bob\plan` (plan); both folders carry AGENTS.md/CLAUDE.md/GROK.md/.cursor rule + skills, every one starting with the CAST IRON harvest rule.
* **IRC** (agent mode): nick `<machine>-<pid>`, joins ONLY `#<machine>`, speaks only there, event-driven relay (blocking read thread injects directly into the console input), answers PING/CTCP/fleet `ping`.
  IRC lost -> kill ONLY the agent tree it started, exit 3, no reconnect. Hang (input injected, then no CPU/IO for 300 s) -> kill tree, NEW agent after 5/15/45 s backoff, max 3 per 30 min (then exit 5), every restart logged.
  Inject logging (FR #86): `worker.log` keeps the **full** `relay: injected FROM ...` line (no mid-URL cut); the same payload is written to `run_dir/last-from.txt` for hang-restart recovery.
  **FR #2380:** agent child env gets `BOB_OUTBOX` / `BOB_SHOP` / `BOB_NICK`; every injected `FROM` ends with `[outbox: <run_dir\outbox.txt>]` so context compaction cannot send ACK/DONE to the ear's `home\outbox.txt`.
  **FR #2383:** if a FR/MRB/UAT assign is injected and no ACK hits the run-dir outbox, re-inject an outbox reminder after `BOB_WORKER_ACK_MISS_REMIND_S` (default 180s), then recycle a NEW agent after `BOB_WORKER_ACK_MISS_RECYCLE_S` (default 900s).
  **FR #2406:** PyInstaller one-file ob-worker.exe stores markers such as ree-rx / _OUT_FREE_RX inside the PYZ — outer-PE Select-String false-fails; extract pyc or run BoredEmitter free-rx tests / outbox GIVEUP for pack UAT.
  **FR #995:** each successful outbox drain logs `outbox: sent PRIVMSG #<shop> (N chars): <scrubbed preview>` so a sending seat is not mistaken for stuck-at-last-bored.
  **FR #994:** Jeeves ``<nick>: nothing queued`` is injected as `FROM` like an assign (so the agent can confirm the wire). If the agent is not ready yet (startup grace) the line is **held** and logged `relay: held nothing-queued`; if console inject fails, `last-from.txt` is still written and the log says `relay: inject failed for nothing-queued`. Operators: Halloy showing `nothing queued` with no `relay: injected` means check for `held` / `inject failed` lines — the seat is not necessarily deaf.
* **`!bored`** (t770u): posted by the exe only, exactly like the agent watcher (`Watch-AgentHealth` FR #100): on ready, right after DONE, idle 120 s then every 180 s, never while an ACK is open (<45 min) or the agent is (re)starting; never after IRC loss; an agent-written `!bored` is refused.
  Jeeves then assigns in `!focus` order; ACK marks the seat doing, DONE marks it idle. Exact lines: `bobiverse-bob-job-irc`.
* **Exit codes**: 0 ok / window closed, 2 IRC unreachable at start (no agent started), 3 IRC lost, 4 no agent or key cancelled, 5 restart limit, 6 launch failed, 64 usage.

## Installer / updater

The MSI lays `worker\bob-worker.exe`, `worker\` and `plan\` (skills, AGENTS, generated CLAUDE/GROK/.cursor), `tools\Get-BobAgentFuel.ps1`. Repo installs and `Sync-BobiverseFromRepo.ps1` build the folders with `Sync-BobiverseAgentFolders` (never deletes `plan\work` or a running exe; the exe only ever arrives with the MSI).
The self-updater applies the MSI; running seats use their run copy and are not killed.

## Port notes for agentic_build (the tray is vendored from there)

`third_party/bob-tray/tools/Watch-BobTray.ps1` changes (see `docs/agentic_build-port-tray-agent-plan.patch`): removed `Build-BobTrayAgentsMenu`, `Build-BobTrayPlanMenu`, `Start-BobTrayPlanAgent`, `New-BobTrayPlanWorkspace*`, `Get-BobTrayPlan*` (the `%USERPROFILE%\BobPlans` flow);
added `Start-BobTrayWorkerExe`; the menu is two plain items. New file `tools/Get-BobAgentFuel.ps1`. **`Sync-BobTrayFromAgenticBuild.ps1` overwrites `Watch-BobTray.ps1` from the pin** - re-apply the patch (or port it upstream first) or the old submenus return. The live-seat list that sat under `Agents` is gone (seats are listed by the watcher tooling; #32 skip unchanged).

## Not verified live (needs a person at a desktop)

Console input injection into the raw-mode Cursor / Grok TUIs; a real Ergo registration with a `<machine>-<pid>` nick and PASS only; a real hung agent; MSI upgrade/uninstall with a running seat; Windows Terminal as the console host.

## UAT job flow (t820u, per repo since t853u)

UAT is per **repo**: Jeeves assigns `UAT owner/repo#0` once - and only when - every issue of the repo is closed (excluding needs-human, boards/mrb-home, harvest/skill records) and every PR is merged; never one UAT per PR. The seat should have implemented none of the cycle's merged PRs. The worker's `UAT` job (skill `bobiverse-bob-job-uat`, with its mermaid diagram) verifies the merged product against the **VISION** (`bob/VISION.md`, FR #1615; fleet umbrella remains `common/docs/vision.md`) and any specs, then branches on the gaps:
**gaps** -> one FR per gap filed through the intake (`Report-BobiverseIntakeIssue.ps1 -Kind fr`), verdict `UAT FAIL`, **no release**; **no gaps** -> documentation and READMEs updated (one docs PR), `VERSION` bumped, `Pack-BobiverseRelease.ps1`, `gh release create`, verdict `UAT PASS`.
The wire contract is unchanged: `ACK UAT owner/repo#0`, then `DONE UAT owner/repo#0 PASS|FAIL [url]` (or `NACK` / `GIVEUP`) in the worker's own `#<machine>`; Jeeves/the chair only does queue bookkeeping and never verifies, files or releases.

## Issues close with their PR (t826u)

* **FR**: the PR body carries `Closes <owner>/<repo>#N` (full form) for the originating issue; the worker checks `closingIssuesReferences` before `DONE FR`.
* **MRB**: PASS merges the PR (and its one docs/fix PR) when the assigned MRB authorises it; otherwise it confirms the `Closes` link. If the issue is still open after the merge (non-default base branch, missing link) the worker closes it with a comment (PR url + verdict). `DONE MRB` only once the issue is closed or linked. **FR #791:** `gh issue close N --body-file` is an unknown flag — use `-c` / `--comment` (never `--body-file` on close; that flag is for `gh pr create` / `gh issue create`).
* **Duplicates (t857u)**: a worker that opens a PR searches the open issues/FRs for duplicates of what it fixes, comments `Duplicate of #N / fixed by PR #M`, closes them as not planned and lists them in the PR body (`Duplicates closed:`; real extra issues get their own `Closes <owner>/<repo>#D`). The MRB verifies the line and closes any it finds. Never `needs-human` / board issues.
* **Queue (chair)**: an `issues closed` webhook drops the issue's FR/PR rows (FR #180 point 4, also the 15-minute GitHub resync); a merge queues no UAT row (UAT is per repo, see above). `gitclaim.extract_closes_issue_ids` understands `Closes #N` and `Closes owner/repo#N` (another repo's link is ignored).

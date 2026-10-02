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

## UAT job flow (t820u)

The worker's `UAT` job (skill `bobiverse-bob-job-uat`, with its mermaid diagram) verifies the merged product against the **VISION** (`docs/vision.md`) and any specs, then branches on the gaps:
**gaps** -> one FR per gap filed through the intake (`Report-BobiverseIntakeIssue.ps1 -Kind fr`), verdict `UAT FAIL`, **no release**; **no gaps** -> documentation and READMEs updated (one docs PR), `VERSION` bumped, `Pack-BobiverseRelease.ps1`, `gh release create`, verdict `UAT PASS`.
The wire contract is unchanged: `ACK UAT owner/repo#N`, then `DONE UAT owner/repo#N PASS|FAIL [url]` (or `NACK` / `GIVEUP`) in the worker's own `#<machine>`; Jeeves/the chair only does queue bookkeeping and never verifies, files or releases.

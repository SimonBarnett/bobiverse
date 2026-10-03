<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path README.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# agentic_build

Any Grok Bot starts git tasks on named machines. Skill: `.grok/skills/grok-build-fleet`. Grok Bot desktop runs on every build box; `grok.exe` is the Windows logon user (MSSQL integrated auth).

- Git task: `Start-BobBuild -Task git` (optional `-Machine` / `-Fuel`). `Select-BobGitWorker` picks a `(machine, fuel)` pair. Fuels: `cursor-models` (shared Cursor Models top-bar pool), `grok-build`, `copilot`, `grok-bot`, `on-demand`.
- Pull worker `tools/Watch-BobJobs.ps1` (logon task, not a Windows service). Tray: `tools/Watch-BobTray.ps1`.
- Named bots (`-Agent Bob`) still use the Grok Bot API. Form Prep stays `--rules`, never `--always-approve`, pin `-Fuel grok-build`.
- Off-DEV Fake-Grok never touches live bots or GitHub. DUMB / 2012 is not a git-task worker.
- **GitHub posting readiness (FR #11 / #34):** `Get-BobGhPostingReadiness` / `gh_posting` on health, capacity, tray, and box-usage. `Select-BobGitWorker -Kind mrb` skips machines with `issue_posting_ready=false`. Token contract: `GH_TOKEN` (or `GITHUB_TOKEN`) with `issues:write` + `pull_requests:write` — never commit secrets. `Install-BobFleet` provisions `gh` or reports not-ready.

## Bob functional-spec build loop

Skills (copied by Install-BobFleet into `~\.grok\skills`):

| Skill | Only job |
|---|---|
| bob-spec-intake | Park FR issue + `/docs` md |
| bob-build-dispatch | Write plan + `Start-BobBuild -Task git` |
| bob-job-loop | `Start-BobBuildLoop.ps1` retry + PASS notify |
| bob-mrb-worker | STANDARD MRB process: tests-first; PASS docs review then merge; FAIL one fix PR |
| bob-hostile-mrb / cursor-mrb-dev | Hand off MRB boards; worker steps -> bob-mrb-worker |
| grok-build-fleet | Start/monitor/stop; picker; heal `Watch-BobJobs` |
| bob-build-loop | Pointer to the five rows above (no separate ritual) |
| start-bob-copilot | Hand GitHub repo work to Copilot (`Start-BobCopilot.ps1`) |
| start-bob-cursor | Hand git task to Cursor Agent (`Start-BobCursor.ps1`) |
| unstick-grok-bot | Unstick a named Grok Bot Temporal hang |
| bob-restart-worker-seat | Diagnose slow vs hung vs out-of-tokens; fresh-session restart (ask first) |
| bob-irc | Fleet `#bobiverse` on Ergo `irc.ntsa.uk:6697` |
| setup-github-webhooks | How to add GitHub repo hooks (`/bob/v1/git`) |
| setup-ssl-certs | How to issue IIS Let's Encrypt with win-acme |

When another agent cannot complete a task, they write a **functional specification** and send it to **Bob**. Feature work arrives as a **GitHub issue** plus `/docs` markdown. Bob orchestrates; he does **not** implement and does **not** write the hostile MRB in-session. Both the PR and the MRB are handed to a worker agent.

**Fuel (no judgment):** if Cursor Models remaining > 0, use Cursor Models (Cursor Grok + Composer). If remaining is 0, use grok.exe. Never Other Models. Copilot only with `-AllowCopilot`. Tray top bar must show that Cursor Models remaining %.

**PR workers:** Cursor **`composer-2.5`**, or grok.exe **`build0.1`** when listed else **`grok-4.5`**. **MRB:** Cursor Grok **`grok-4.6`** on cursor-agent, else grok.exe **`grok-4.6`**. Every worker opens a **PR**. **FR mode never self-merges** (FR #343). STANDARD MRB: `bob-mrb-worker` on a **different** seat — after tests and hostile review PASS, review docs for stale behavior; open exactly **one** docs PR against `main` when needed and merge it with the original, otherwise merge as before. FAIL: exactly **one** fix PR then merge original + fix. Only Bob stamps UAT.

### Fleet machines (registry ids)

Canonical list: `config/fleet-registry.json`. Clone paths on this legion:

| id | Role | Clone path |
|---|---|---|
| `ionos` | VPS; Ergo host; pull worker | `C:\\ai\\agentic_build` |
| `marchhare` | Dual-homed build box | `D:\\ai\\agentic_build` |
| `flamingo` | Club Madeira seat | `C:\\src\\agentic_build` |
| `ce-priority-dev1` | Form Prep / Priority Azure | `C:\\src\\agentic_build` |

IRC status uses nick `bob-dev1` for `ce-priority-dev1`. Job audit lines: `docs/job-audit-line.md`. GitHub protection intent: `docs/github-main-protection-checklist.md`.

### New product (fresh functional spec)

1. Create a **new public** GitHub repository under `SimonBarnett`.
2. Commit the functional specification under `/docs`.
3. From the spec, write a **full detailed build and test plan** a build agent can execute; commit it under `/docs`.
4. `Start-BobBuildLoop.ps1` (skill `bob-job-loop`) starts the git worker, hands off MRB, retries failed cursor/grok jobs, and prints `DONE` on PASS-nits. Or `Start-BobBuild -Task git` (picker: Cursor Models remaining > 0, else grok-build) and hand each row yourself.
5. Worker implements on `work/<job>` and **opens a PR**. Never push `main`. Never merge (**FR #343** FR mode: open PR → stop; other seat MRBs).
6. Bob **hands off** hostile MRB on that PR (`Start-BobBuildLoop.ps1` or `tools/Start-BobMrbHandoff.ps1`) to a **different** seat (or fresh MRB session). The worker posts a **new** GitHub issue `MRB FAIL|PASS-nits: <slug> <sha>` (labels `mrb` + `mrb-fail` or `mrb-pass`). Missing features get parked as new FRs. No MRB PDF.
7. MRB follows `bob-mrb-worker`: use `gh pr checkout` in a temp worktree; read intent; add NEW tests before testing; run the tests; then hostile review. After a PASS, review README, skills, `docs/`, mermaid diagrams, and usage/help text for stale behavior. If stale, open exactly **one** docs PR against `main` and merge it with the original; if docs are fine, merge as before. **FAIL:** open exactly **one** fix PR with the fix, then merge original + fix (not multiple fix PRs). Jeeves announces. Close the source issue/FR after PASS, hand off to a separate UAT worker, and only **Bob** stamps **ready for human UAT**. Pack: `docs/fr-mode-no-self-merge.md`. Guard: `tools/fr_self_merge_guard.py`.

### Feature request (extends existing repo)

1. Must **not break** previous versions.
2. Add new work in versioned folders such as `v2/`, `v3/` (keep prior folders intact).
3. Park `docs/feature-request-<slug>-YYYY-MM-DD.md` plus a GitHub issue (`bob-spec-intake`).
4. `Start-BobBuildLoop.ps1` (or `Start-BobBuild -Task git`) to implement and **open a PR**.
5. Same PR/MRB transaction as above (new issue per PR head; `bob-mrb-worker` PASS docs review then merge, with exactly one docs PR when stale / FAIL one fix PR then merge both; Bob stamps UAT). Git is the source of truth.

### Flow

Proposed pair model (`#175` — Simon check this logic before more impl):

```mermaid
flowchart TB
  IN["FR or functional spec for a new repo\nusually turns up"]
  IN --> PARK["bob-machine parks issue + /docs"]
  PARK --> CHAIR["bob-machine is the grok chair\ninstalled on every box\nbobiverse skills"]
  TIX["Bob also checks outstanding tickets\nevery 2 hours during business hours\nand assigns them"]
  TIX --> ASSIGN
  CHAIR --> DESC["#channel description = assigned repo\nchange when the repo changes"]
  CHAIR --> PAIR["Bob MUST start agents with\nIRC + build skills\nBob directs them to JOIN IRC"]
  CHAIR --> ASSIGN["Bob orders and assigns MRB vs dev\ncan assign any idle over 20s agent on bobiverse"]
  CHAIR --> IDLEMRB["If Bob not responding:\nidle worker MRBs the open PR"]
  CHAIR --> RT["Bob decides which to invoke:\nlocal agent vs agent.com"]
  RT --> PAIR
  CHAIR --> MON["Bob monitors processes in flight\nrestart if they stop responding"]
  CHAIR --> PING15["Every 15 min Bob pings own shop\ncheck connections / online\nintervene if workers stalled"]
  CHAIR --> USE["Each bob webhooks identity +\nreal pools only: grok chat / high cost / low cost\n+ local xAI grok weekly\nNOT Club Madeira or Smart Catalogue pools"]
  USE --> MIN["Each pool: remaining % + next period start\n0 is 0 not n/a; n/a only if unavailable\nMUST webhook; lesser of Cursor variance"]
  CHAIR --> JEEVES["Every time Bob calls !bobiverse:\nif Cursor or local xAI changed, POST webhook"]
  CHAIR --> OPS["bob-machine is ops in own shop channel\nJeeves is ops in #bobiverse"]
  MIN --> TRAY["Control systray shows proper Cursor meters\ngrok chat / high cost / low cost\nremaining % + next period; 0 is 0"]

  subgraph PAIRBOX["One repo, two workers — persist until idle a few minutes"]
    WA["Worker A: implement next PR\nopen PR only — never self-merge\nFR #343\ndev model: LESS"]
    WB["Worker B: MRB that PR (other seat)\nMRB model: MEDIUM\nPASS: review docs\nmerge one docs PR if stale\nFAIL: one fix PR\nbob-mrb-worker"]
  end

  PAIR --> WA
  PAIR --> WB
  ASSIGN --> WA
  ASSIGN --> WB
  MON -.-> PAIRBOX
  WA -->|"A does the work itself\nopen PR; never invoke another agent"| WB
  WB -->|"B MRBs itself; never invoke another agent\nFAIL: exactly one fix PR; merge original + fix"| FIX["A FIXes its own PR\nthen B re-MRBs"]
  FIX --> WA
  WB -->|"PASS-nits: docs OK or one docs PR merged"| NEXT{"More PRs / FRs?"}
  NEXT -->|yes| SWAP["Implementer moves to next PR\nother worker MRBs"]
  SWAP --> WA
  NEXT -->|both idle a few minutes| HARV["Bob reminds workers to harvest skills"]
  HARV --> STOP["Bob may terminate the pair"]

  WA --> POST["Workers MUST POST working_on to webhook\nNO channel PRIVMSG — webhook only"]
  WB --> POST
  POST --> DIG["Digest updates"]
  DIG --> SAY["Bob reads digest\ndev complete / MRB complete\nreports to #bobiverse"]
  NEXT -->|PASS-nits and ready| UAT["Bob chair only: UAT skill\nUAT model: MORE\nworkers never stamp UAT"]
```

Full product loop (park / fuel / build) still uses `bob-spec-intake` +
`bob-build-dispatch` + `bob-job-loop`. The diagram above is the **STANDARD**
MRB worker process (`bob-mrb-worker`).

### Talking to build agents

Use **BobBridge** for job lifecycle (`Start-BobBuild -Task git`, `Send-BobBuildSpec`, `Get-BobBuild`, `Stop-BobBuild`).

Fleet status is **[agentic_irc](https://github.com/SimonBarnett/agentic_irc)** on private Ergo `irc.ntsa.uk:6697` (`#bobiverse`, skill `bob-irc`).

- `scripts/irc_agent.py` — TLS join, PASS from env / connect file, announce AGPK.
- `scripts/seal.py` — SEAL v2 for secrets (TOFU-pinned DH-AAD). Never send secrets in cleartext; never dump `inbox/*.bin` into chat.
- IRC verbs (no vendor names): `SPEC` `WAIT` `BUILD` `PUSH` `MRB` `FIX` `UAT`. Pass the MRB issue URL on `FIX`.
- Two agents on one box need different `--home` / `AGENTIC_IRC_HOME` directories.

### Guardrails

- Bob orchestrates and stamps UAT. Workers open PRs. The dispatcher hands each PR to a **different** worker for MRB (`Start-BobMrbHandoff`, new job, `-Kind mrb`). The implementer never reviews or merges their own PR. After tests and hostile review PASS, the MRB agent reviews docs; stale docs become exactly one docs PR against `main`, merged with the original, while docs OK merges as before. FAIL: exactly one fix PR then merge both (`bob-mrb-worker`). No in-session MRB or implementation.
- Cursor Models remaining % is the tray top bar and the fuel gate, not a fleet machine id, not Grok Bot Sand, not Other Models.
- New product repos are **public** under `SimonBarnett` unless Simon says otherwise.
- Never mark ready for human UAT until Bob stamps that phrase on the issue.

## Bob Fleet tray (FR #346)

- **Restart watcher** (systray menu): full local reinstall via `tools/Invoke-BobFleetReinstall.ps1` (pull/stash/ff, tools, skills, deploy SHA, restart; busy seats wait by default). Scope is this machine only — not Ergo/Jeeves.
- **Bob Fleet** Desktop/Start Menu shortcuts: `tools/Start-BobFleetTray.ps1` (single-instance; no second tray).
- Skill: `bob-fleet-tray`. Tests: `tests/Test-BobFleetReinstall-FR346.ps1`.

## Bob Fleet process diagrams

These mirror the saved Bob Fleet skills. The pair-model chart under **Flow** above is still the `#175` proposal; the charts below are the current per-skill processes.

### 1. MRB worker review steps (`bob-mrb-worker`)

An MRB worker checks out the PR in a temporary worktree, adds new tests, runs every test, performs the hostile review, then checks documentation before merging a PASS.

```mermaid
flowchart LR
  A[gh pr checkout<br/>temp worktree] --> B[Read PR intent]
  B --> C[Add NEW tests]
  C --> D[Run tests +<br/>hostile review]
  D -->|PASS| E[Review docs vs<br/>new behaviour]
  E -->|docs stale| F[One docs PR<br/>README, skills, diagrams]
  E -->|docs OK| G[Merge PR]
  F --> G
  D -->|FAIL| H[One fix PR]
```

_After a PASS, check whether any documentation still describes the old behaviour; if so, open one docs PR and merge it with the original._

### 2. Idle worker `!bored` → Jeeves assigns → accept-on-ACK (`bob-git-accept`)

A worker idle for more than 2 minutes must say `!bored` in its own `#{machine}`. **Jeeves assigns** the next job to that nick (`<nick>: <TYPE> <repo>#<n> <url>`, `!focus` order). The job is marked accepted only when the worker ACKs. Source of truth: [gh-Jeeves README](https://github.com/SimonBarnett/gh-Jeeves#readme) (FR #106).

AgentMonitor **watch seats** get `!bored` from the monitor itself (start / after DONE / idle; no LLM) — see AgentMonitor FR #100 / #108 and `tools/Watch-AgentHealth/Watch-AgentHealth.ps1`. CAST IRON (Simon 2026-09-26): the model never posts `!bored`; only the seat monitor does.

```mermaid
flowchart TD
  A[Worker idle] --> B{Idle > 2 min?}
  B -->|yes| C[MUST !bored in #machine]
  C --> D[Jeeves assigns next job TO this nick]
  D --> E{Worker ACK?}
  E -->|yes| F[Mark accepted + busy → FR/MRB/UAT]
  E -->|no| G[Stays unaccepted]
  F --> H[DONE → done + idle; clear working_on]
  H --> A
```

### 3. Jeeves chair: unaccepted queue digest, `#bobiverse` announces, `!bored` → assign (`bob-jeeves-chair`)

Jeeves reads the webhook's unaccepted queue, announces GIT work on `#bobiverse`, and **assigns** the next job to whichever trusted `{machine}-<pid>` worker says `!bored` in that shop. Ear OFFER path is retired (FR #106).

```mermaid
flowchart TD
  A[Digest webhook unaccepted queue] --> B[Jeeves]
  B --> C["Announce GIT to bobs on #bobiverse only"]
  D[Worker: !bored in #machine] --> E[Jeeves assigns next job]
  E --> F["One line: nick: TYPE repo#n url"]
  F --> G{Worker ACK?}
  G -->|yes| H[Mark accepted + busy]
  G -->|no| I[Stays unaccepted]
  H --> J[That worker runs the mode]
```

### 4. FR → MRB → UAT handoff

An issue or FR is announced by Jeeves, assigned when a shop worker says `!bored` (Jeeves assigns; scripts-only / Sand-empty path is the same), built as a PR, reviewed by a different worker where possible, then after PASS its documentation is checked and any stale docs are corrected in one docs PR merged with the original before a separate UAT worker is handed off; or it is fixed with one extra PR while the issue stays open.

```mermaid
flowchart TD
  A["Issue / FR opened"] --> B["Jeeves announces on #bobiverse"]
  B --> C["Idle worker !bored in shop #machine"]
  C --> D["Jeeves assigns next job from unaccepted queue"]
  D --> E["Worker ACK → accepted + busy"]
  E --> F["FR worker implements and opens a PR"]
  F --> G["Jeeves announces the PR on #bobiverse"]
  G --> H{"2 or more workers available?"}
  H -->|yes| I["MRB by a different worker"]
  H -->|no| J["Same seat may continue into MRB"]
  I --> K{"MRB verdict"}
  J --> K
  K -->|PASS| L["Review docs; merge PR + one docs PR if stale; close issue"]
  L --> M["Separate UAT worker runs UAT"]
  M --> N["Only Bob stamps UAT"]
  K -->|FAIL| O["Open exactly one fix PR"]
  O --> P["Merge original PR and fix PR"]
  P --> Q["Issue stays open, no UAT"]
```

## Off-DEV (no real grok)

```powershell
powershell -NoProfile -File .\\tools\\Test-Pack.ps1
```

Points `BOB_GROK_EXE` at `tools/Fake-Grok.ps1` and uses a temp `BOB_BRIDGE_HOME`. Must not touch `%USERPROFILE%\\.grok\\bob-bridge`.

## Use

```powershell
Import-Module .\\src\\BobBridge.psd1
Register-BobMachine -Id ionos -CwdRoots C:\\ai
Start-BobBuild -Task git -Cwd C:\\ai\\agentic_build -Goal 'ping' -Profile generic
Start-BobBuild -Machine ionos -Fuel grok-build -Cwd C:\\ai\\agentic_build -Goal 'ping' -Profile generic
powershell -NoProfile -File .\\tools\\Watch-BobJobs.ps1 -Once
Get-BobBuild -JobId <id>
```

Install the logon watcher + user skill copy (not a Windows service):

```powershell
powershell -NoProfile -File .\\tools\\Install-BobFleet.ps1 -MachineId marchhare
```

Form Prep on DEV1 still uses grok.exe:

```powershell
$env:BOB_GROK_EXE = "$env:USERPROFILE\\.grok\\bin\\grok.exe"
Start-BobWorker -Cwd D:\\work\\formprep -Prompt 'PONG' -Profile formprep
```

`BOB_TRANSPORT=cli` forces grok.exe. `BOB_GROK_BOT_HOME` overrides the Grok Bot profile dir.

## Layout

```
agent_readme.md  handover for any Grok Bot (attach this)
.grok/skills/    grok-build-fleet, start-bob-copilot, bob-mrb-worker, bob-hostile-mrb, bob-*
docs/            feature requests, plans, harvest log
schemas/         health overlay status completion prompt-packet
src/             BobBridge module (Public/Private)
config/          default.json, bobiverse.json, bob-seats.json
tools/           Watch-BobJobs, Watch-BobTray, Start-BobBuildLoop, run-bob-build-loop, Start-BobMrbHandoff, Test-Pack
tests/           last-dev-run.md template
```

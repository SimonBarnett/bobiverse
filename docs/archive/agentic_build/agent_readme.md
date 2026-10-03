<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path agent_readme.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Agent handover — Grok Build fleet

You dispatch **git-task workers** on named Windows machines. Cursor Models
while remaining > 0, else `grok.exe`. Workers **open PRs**. You do not WinRM,
you do not install a Windows service, and you do not put SQL passwords in prompts.

Grok Bot desktop is running on every build machine. `grok.exe` runs as the **Windows logon user**. That user already has MSSQL (integrated auth).

Repo: `https://github.com/SimonBarnett/agentic_build`  
Canonical machine table (must match `README.md` and `config/fleet-registry.json`):

| id | Role | Clone path (this house) |
|---|---|---|
| `ionos` | VPS; Ergo host; pull worker | `C:\ai\agentic_build` |
| `marchhare` | Dual-homed build box | `D:\ai\agentic_build` |
| `flamingo` | Club Madeira seat | `C:\src\agentic_build` |
| `ce-priority-dev1` | Form Prep / Priority Azure | `C:\src\agentic_build` |

`-Machine` is a registry **id**, not a hostname. IRC status nick for `ce-priority-dev1` is `bob-dev1` on `#bobiverse`.

Skills (auto-load on grok.exe / Grok Bot): `.grok/skills/grok-build-fleet`, `.grok/skills/unstick-grok-bot`, `.grok/skills/harvest-agent-skills`.

## IRC (fleet status)

Private Ergo `irc.ntsa.uk:6697`, channel `#bobiverse`. Skill stub `bob-irc` (canonical copy in **agentic_irc**). Docs: `docs/bobiverse.md`. Do not open IRC from CI.

## Load (local-exec on the target computer)

```powershell
$repo = if (Test-Path 'D:\ai\agentic_build') { 'D:\ai\agentic_build' } elseif (Test-Path 'C:\ai\agentic_build') { 'C:\ai\agentic_build' } else { 'C:\src\agentic_build' }
Import-Module "$repo\src\BobBridge.psd1"
```

The pull worker `tools\Watch-BobJobs.ps1` (logon task) claims **this** machine’s inbox and runs the build. If you enqueue for another id, that machine’s watcher runs it.

## BobBridge exports (agents)

**Job + fuel + machine (document these to workers):** `Get-BobMachines`, `Register-BobMachine`, `Get-BobHealth`, `Get-BobCapacity`, `Select-BobGitWorker`, `Start-BobBuild`, `Get-BobBuild`, `Get-BobBuilds`, `Send-BobBuildSpec`, `Stop-BobBuild`, `Get-BobJobModel`, `Invoke-BobFleetTick`, `Start-BobWorker`, `Send-BobPrompt`, `Get-BobResult`, `Stop-BobWorker`, `Test-PromptSecrets`.

**Tray + IRC (only `bob-fleet-tray` / `bob-irc` skills):** `Get-BobTrayHover`, `Get-BobTrayBarPaint`, `Get-BobTrayTipPlacement`, `Get-BobWeeklyRemaining`, `ConvertTo-BobIrcPoint`, `Write-BobIrcStatus`, and related `*-BobIrc*` helpers in `BobBridge.psd1`.

## Git task loop (skills, not one mega-skill)

| Skill | Only job |
|---|---|
| `bob-spec-intake` | Park FR issue + `/docs` md |
| `bob-build-dispatch` | Write plan + `Start-BobBuild -Task git` |
| `bob-job-loop` | `Start-BobBuildLoop.ps1` retry + PASS-nits notify |
| `bob-hostile-mrb` / `cursor-mrb-dev` | Hand off MRB; PASS reviews docs and merges one docs PR if stale; FAIL → one fix PR then merge both |
| `grok-build-fleet` | Start/monitor/stop; picker; heal `Watch-BobJobs` |
| `bob-build-loop` | Pointer to the rows above |
| `bob-repo-pair` | Two persistent dev+MRB workers per repo (#175); chair `bob-{machine}` |

## Repo pair (optional path, #175)

When Bob owns a repo with two shop workers instead of one-shot jobs:

`Start-BobRepoPair`, `Get-BobRepoPair`, `Update-BobRepoWorkerWorkingOn`,
`Invoke-BobRepoPairTick`, `Test-BobRepoPairSelfMrb`, `Get-BobRepoPairBobiverseReport`.
Skill `bob-repo-pair`. v1 `Start-BobBuildLoop` stays until Simon switches the repo.

## Start a build

```powershell
Start-BobBuild `
  -Machine marchhare `
  -Cwd $repo `
  -Profile generic `
  -Goal '<what to do>' `
  -Constraints @('<hard limit>', '<hard limit>') `
  -Success '<how we know it worked>' `
  -ReplyChannel '<your Grok Bot name: Bob, Haitch, Merc, …>'
```

Git task with picker: `Start-BobBuild -Task git -Goal '...' -Profile generic`.

Tell the human the `jobId`. Then poll:

```powershell
Get-BobBuild -JobId <jobId>
Get-BobBuilds -Machine marchhare
```

`lane` is `inbox` → `running` → `outbox`. `state` is `running` / `done` / `failed` / `blocked` / `stopped`. Outbox includes `completion.status` (`ok`/`failed`/`blocked`/`stopped`) and `completion.summary`.

**Job audit:** each fleet outbox completion appends one JSON line to `{BOB_BRIDGE_HOME}\job-audit.jsonl` with `jobId`, `machine`, `fuel`, `model`, `kind`, `prUrl`, `mrbIssue`, `sha`, `status` (fields may be empty on Fake-Grok). `Start-BobBuildLoop.ps1` appends again on MRB PASS-nits.

Follow-up spec on a live job:

```powershell
Send-BobBuildSpec -JobId <jobId> -Prompt '<extra instruction>'
```

Stop:

```powershell
Stop-BobBuild -JobId <jobId>
```

The worker also pings `-ReplyChannel` with queued / running / blocked / done. Off-DEV Fake-Grok never pings live bots.

## Profiles

| Profile | When | Hard rules (also injected into grok.exe `--rules` unless yolo) |
|---|---|---|
| `formprep` | Priority Form Prep on `ce-priority-dev1` | DEV only. Never SQL-flip UPD. Never AllUnprepared. Never commit secrets. MSSQL = Windows logon (integrated). Never SQL passwords. **No `--yolo` / `--always-approve`.** |
| `teams` | Teams audio / hours | No AccessMedia.All. Do not claim fixture speak is audible. |
| `mud` | MUD | No spend. Stay on configured host. |
| `generic` | Default | No production deploys. No force-push. |

## Spec contents

`goal` / `constraints` / `success` are the spec. Keep secrets out: `password=` or `XAI_API_KEY` assignments (including `export XAI_API_KEY …`) in the goal are refused.

Point `cwd` at a repo the target machine can see, under that machine’s `cwdRoots`.

## What you tell the human

1. Machine + profile + `jobId`.
2. When `lane=outbox`: `state`, `completion.status`, `completion.summary`. Quote evidence, do not invent `ok`.
3. If `blocked` or `failed`: `completion.needs_human` and `next_suggested`.

## Do not

- WinRM / SSH / RDP to start grok.
- Windows service / SCM.
- `--always-approve` or `--yolo` on formprep.
- SQL passwords, `XAI_API_KEY=`, or `password=` assignments in packets.
- Claim a machine by hostname; use the id.
- Touch `%USERPROFILE%\.grok\bob-bridge` from Fake-Grok tests.
- Mark **ready for human UAT** (Bob only).

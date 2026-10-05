# bobiverse

Fleet IRC product: single-file MSIs for **Jeeves** (Ergo + chair), **Bob** ears, and **airc** consoles.

| MSI | Service(s) | Nick | Install tree |
|-----|------------|------|--------------|
| `jeeves-*.msi` | `BobIrcd` + `ircJeeves` | `Jeeves` | `<ai root>\jeeves` (+ Ergo → `<ai root>\ergo`) |
| `bob-*.msi` | `ircBob` (+ tray / Watch-AgentHealth) | `Bob-{machinename}` | `<ai root>\bob` |
| `airc-*.msi` | `Airc` | `{machinename}_console` | `<ai root>\airc` |

## Repository layout

The repo is split per service; each folder holds that service's scripts, skills, agent layer, docs and tests.

```text
jeeves/   scripts/ (Install-Jeeves, Start-Jeeves, Install-BobIrcd/Chair/Webhooks, Watch-*) .grok/skills/ AGENTS.md docs/ tools/ tests/
bob/      scripts/ (Install-Bob, Start-Bob*, bob_worker.py, Build-BobWorker) .grok/skills/ AGENTS.md agents/{worker,plan} docs/
          tray/ (the systray: tools/ src/ assets/ config/ dialogs/ = bob-about + bob-status exes) agentwatcher/ (Watch-AgentHealth) tests/   (t829u: first-class bob sources; staged/installed trees stay flat)
airc/     scripts/ (Install-Airc*, Start-AircConsole*, airc_console*.py) .grok/skills/ AGENTS.md docs/ packaging/Product.wxs tests/
common/   scripts/ (Bobiverse-Common, Pack-BobiverseRelease, Fetch-*, Update/Sync/Check, repo_layout.py, the shared python engine: irc_agent.py wire.py ...)
          .grok/skills/ (harvest, fleet-ops) docs/ third_party/{nssm,ergo,wix}/ VERSION tests/ (tests only; repo_layout.py lives in common/scripts — FR #963)
config/ dist/   not tracked (gitignored secrets / build output)
```

The **staged and installed trees stay flat** (`<root>\scripts`, `<root>\.grok\skills`, `<root>\docs`, `VERSION`): `Pack-BobiverseRelease.ps1`
composes `stage\scripts` from all four `*/scripts` dirs, so installers, NSSM services, the updater and the MSIs are unchanged. The python modules
form one import graph (`irc_agent` imports the chair/shop/talk modules), so they live together in `common/scripts`.
Dev: run `pytest` from the repo root (`conftest.py` puts every `*/scripts` on `sys.path`); build a runnable flat tree with
`common\scripts\Pack-BobiverseRelease.ps1 -Product bob -SkipMsi -KeepStage -SkipWorkerExe` and run the installer from `<stage>\scripts`.
Heads-up: an install that still has the pre-split `Sync-BobiverseFromRepo.ps1` finds no `scripts\` in a split clone and syncs nothing until it has
taken the next MSI release.

## The `<drive>:\ai` root (no hard-coded `C:\ai`)

Fleet trees live under `<drive>:\ai` (`<ai root>\bob`, `\jeeves`, `\airc`, `\ergo`, `\bobiverse` clone) but the drive is **not always C:** (MarchHare keeps repos and agent homes on `D:\ai`). Every installer, MSI, updater, Start/Restart script, tray and the worker exe resolve the root the same way:

1. env `BOB_AI_ROOT` (explicit override; MSI: `msiexec /i x.msi AIROOT=D:\ai`),
2. otherwise scan the **fixed physical disks only** (`Win32_LogicalDisk` DriveType 3; removable, network and CD/DVD are ignored) for an existing `\ai` folder,
3. several found: prefer the one already holding `bob`/`jeeves`/`airc`/`ergo` install folders, then the one the fleet services (`ircBob`, `ircJeeves`, `BobIrcd`, `Airc`) already point at, then the system drive, then drive-letter order,
4. none found: `<SystemDrive>:\ai`, created **only** by an installer (never when an `ai` folder exists on any fixed disk).

Implementations (same rules, tested together in `common/tests/test_ai_root_020.py`): `Get-BobiverseAiRoot` / `Get-BobiverseProductRoot` in `common/scripts/Bobiverse-Common.ps1`, `common/scripts/ai_root.py` (worker exe, `gh_filer.py`), `common/packaging/FindAiRoot.js` (MSI immediate custom action: sets `AIROOT`, `INSTALLDIR=[AIROOT]\<product>`, and passes `-InstallRoot` to the post-install script). Scripts that run from an installed tree also use their own location (`<install>\scripts`) before scanning.
## The install dir is a git work tree (repo fast-forward on every start)

On every service start (`ircBob`, `ircJeeves`, `Airc`) `Start-*.ps1` runs `Sync-BobiverseFromRepo.ps1`, which turns `<ai root>\<product>` into a **sparse git work tree** of this repo and fast-forwards it:

| install dir | tracked subtrees (sparse, non-cone) |
|---|---|
| `<ai root>\bob` | `bob/` + `common/` |
| `<ai root>\jeeves` | `jeeves/` + `common/` |
| `<ai root>\airc` | `airc/` + `common/` |

Nothing else of the repo is checked out (no sibling products, no root files). The flat runtime files the services run (`scripts\`, `third_party\`, `docs\`, `.grok\skills\`, `VERSION`, `worker\`, `plan\` ...) are **composed from those subtrees** (`robocopy /XO`, never deleting) and hidden from git by `.git\info\exclude`, so `git status` shows only real edits under `<product>\` and `common\`.

Rules (`Sync-BobiverseWorkTree` in `common/scripts/Bobiverse-Common.ps1`):

* first start: `git init` + `remote add origin` (env `BOBIVERSE_REMOTE`, default this repo) + sparse checkout + `checkout main`; on any failure the half-made `.git` is removed and the installed files keep running;
* later starts: `git fetch` (timeout 120 s with retries, no prompts) then `merge --ff-only origin/main` **only when the work tree is on `main`**. Never `reset`/`stash`/`clean`/`checkout -f`; uncommitted edits, local commits, a feature branch, a detached HEAD or a merge/rebase in progress are left exactly as they are (the fetch still happens). A refused ff is an ALERT, never a failed start;
* after every ff attempt the sync counts `git rev-list --count HEAD..origin/main` and emits **`ALERT sync-behind: HEAD behind origin/main by N commit(s)`** when N > 0 (FR #2470) — so a long-lived service that skipped restarts, or an ff that claimed success while tip still lagged, is visible in the start log;
* offline / git missing / auth failure: the installed version runs unchanged.

**Precedence of the update paths** (dev path first, release path second):

1. `BOBIVERSE_REPO=<clone>` (explicit dev override): that clone is ff'd and copied into the install tree instead of the work tree.
2. The install work tree ff (this section) - new commits on `main` are picked up on the next service restart (or by running `Sync-BobiverseFromRepo.ps1` by hand).
3. Then the MSI release self-update (`Update-BobiverseService.ps1`): acts only if a GitHub release is **newer than the VERSION now installed** (the ff'd tree counts), so it remains the safety net where git/GitHub-git is unavailable.
4. A shared clone `<ai root>\bobiverse` is used only when the work tree cannot be used.

**Opt-out:** `BOBIVERSE_NO_UPDATE=1` (machine env) disables the repo ff, the sync *and* the release check. `BOB_AUTOUPDATE=0` / `<install>\config\autoupdate.disabled` disable the release check only.

Working in the install dir (agents and humans): edit under `<product>\` / `common\` (the flat copies are build output and are refreshed from them), then `git switch -c fix/x`, commit, `git push -u origin fix/x`, open the PR. `Sync-BobiverseFromRepo.ps1 -Product <p>` applies your branch to the running flat tree without a restart. Issues go to the intake with `scripts\Report-BobiverseIntakeIssue.ps1`. Services run as another account than the file owner: `git -c safe.directory=* ...` or `git config --global --add safe.directory <install dir>`. The test-suite needs the full repo (root `conftest.py`): run it from a full clone or a job worktree with `git sparse-checkout disable`, not from a sparse install dir. Sparse FR/MRB trees that keep a partial cone must include `common/scripts` so `repo_layout` imports (FR #963); `*/tests/conftest.py` also adds that path.

### Catch-up / harvest hotpatch when the install lags tip (FR #2470)

`ircBob` / `ircJeeves` / `Airc` only run the ff+recompose path on **service start**. A box that stays up for days can leave `common\scripts` (and the flat `scripts\` copies) hundreds of commits behind `origin/main` — e.g. harvest still using bare `$r.url` under StrictMode after FR #2379 / PR #2385 landed on tip.

Preferred catch-up (install on `main`, clean tree):

```powershell
& <install>\scripts\Sync-BobiverseFromRepo.ps1 -Product bob -InstallRoot <install>
```

That fetch + ff-only + robocopy recomposes flat `scripts\` from `common\` / `<product>\`. Watch the log for `ALERT sync-behind` / `ALERT sync-ff-failed`.

One-file **hotpatch** when ff is blocked (dirty tree or feature branch) but you need tip harvest immediately (UTF-8 **without BOM**; WinPS `-Encoding utf8` writers add a BOM — use `UTF8Encoding(false)`):

```powershell
git -C <install> fetch origin
 = git -C <install> show origin/main:common/scripts/Invoke-BobiverseHarvest.ps1
# UTF-8 no BOM (WinPS Set-Content -Encoding utf8 writes a BOM)
[System.IO.File]::WriteAllText(
  (Join-Path <install> 'common\scripts\Invoke-BobiverseHarvest.ps1'),
  (( -join "
").TrimEnd() + "
"),
  [System.Text.UTF8Encoding]::new(False)
)
& <install>\scripts\Sync-BobiverseFromRepo.ps1 -Product bob -InstallRoot <install> -ComposeOnly
```

Same pattern for `Report-BobiverseIntakeIssue.ps1`. Edit tracked `common\scripts\…`, then `-ComposeOnly`; do not hand-edit only the flat `scripts\` copy (the next sync would overwrite it from a still-stale `common\`).
## Pack

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File common\scripts\Pack-BobiverseRelease.ps1 -Product all
```

## Install (elevated / UAC)

```bat
bob\scripts\Install-Bob.cmd -MachineId marchhare
jeeves\scripts\Install-Jeeves.cmd
airc\scripts\Install-Airc.cmd -MachineId marchhare
```

Or `msiexec /i bob-0.1.1.msi`.

## Behaviour

- `!register <machine>` (Jeeves, Simon/operators) → ChanServ REGISTER
- Registered `Bob-*` gets +o on shop, +h on `#bobiverse`
- Systray/shortcut Restart → departure announce → `Restart-Service ircBob`
- `!assign <worker-nick> <repo> <FR|MRB|UAT> <num>` (Jeeves, verified simon or a Bob-* ear only): Jeeves posts the normal assign line to that idle seat (no self-MRB/UAT, seat not busy, row queued and unaccepted); ACK accepts it. UAT is per repo (`UAT owner/repo#0`): Jeeves queues ONE repo-level UAT only when every issue is closed (excluding needs-human/boards/harvest records) and every PR is merged. See `jeeves/docs/jeeves-commands.md`
- `!recycle` / `!recycle {mid}` on Bob; `!recycle jeeves` on chair (ircJeeves only)
- Service start self-updates to the latest GitHub release (`Update-BobiverseService.ps1`, v0.1.17): token-less check, detached helper downloads + sha256-verifies the MSI, backs up, installs, rolls back on failure, logs to `%ProgramData%\bobiverse\update\<product>\update.log`. Opt out with `BOB_AUTOUPDATE=0` (or `BOBIVERSE_NO_UPDATE=1`, or a `config\autoupdate.disabled` file). Never touches Ergo or seats; always starts the installed version if the check fails.
- ObjectName = fleet user (DPAPI): interactive prompt, `BOBIVERSE_SERVICE_PASSWORD`, `config\service.password`, or **Complete bobiverse service logon**
- Ergo server PASS is **not** in public MSIs (issue #4); place `config\ergo.password` post-install (or pack with `-EmbedErgoPassword` for private builds)
- Bob ear loads `home\nickserv.password` for SASL (`bob-{machine}`) so reserved nicks get `001`
- Quiet MSI `/qn` never prompts for ObjectName password (issue #6); LocalSystem omits `-BobHome` (issue #7)
- First Ergo install seeds `<ai root>\ergo\ircd.yaml` from `default.yaml` until operator TLS/PASS/ChanServ are set

## Post-install

See **[docs/post-install.md](docs/post-install.md)** (ObjectName password, Ergo PASS, NickServ SASL, verify ear/airc).

## Harvest (honesty box)

Using fleet skills binds you to report what you learned or what broke. CAST IRON harvest + intake live in `common/.grok/skills/harvest-agent-skills/SKILL.md` and `common/.grok/skills/harvest/SKILL.md`. Prefer `common\scripts\Report-BobiverseIntakeIssue.ps1` / `Invoke-BobiverseHarvest.ps1`. Never file against archived superseded repos.

## Historical fleet playbooks

Pre-bobiverse READMEs, chair diagrams, and skill books from `agentic_build` / `gh-Jeeves` / `agentic_irc` / `AgentMonitor` / `bob-design-uat` are preserved under [docs/archive/](docs/archive/). They are **not** live runbooks (paths and commands may be stale). Prefer this README, `jeeves/docs/`, `bob/docs/`, and product skills for current behaviour.

## Archived repositories

The canonical archive manifest and replacement map live in [docs/ARCHIVED_REPOS.md](docs/ARCHIVED_REPOS.md). Superseded repositories remain linked there for historical issue/PR provenance; they are never deleted.

Repo: https://github.com/SimonBarnett/bobiverse

# bob-worker-net (.NET 8, FR #9800 / #9806)

Phase 0 scaffold (digest **#9794**) plus Phase 3 Grok spawn (digest **#9797** / epic **#9793**): a console host compiled with the **.NET 8 SDK**, not the in-box Framework 4 `csc.exe` used by tray dialogs.

## Airc min-spec / no-SDK does **not** apply

Tray dialogs (`Build-BobDialogs.ps1`) deliberately use Framework 4 `csc.exe` so airc min-spec machines need no SDK. **`bob-worker-net` is different:**

* Requires the **.NET 8 SDK** on the build machine (`dotnet publish`).
* Publishes a **self-contained win-x64** single-file `bob-worker-net.exe`.
* GitHub Actions uses `actions/setup-dotnet@v4` (see `.github/workflows/build-bob-worker-net.yml`).

Do not replace `dotnet publish` with `csc.exe`. Do not treat this project as an airc no-SDK deliverable.

## Layout

| Path | Role |
| --- | --- |
| `bob/worker/dotnet/BobWorkerNet.csproj` | SDK-style `net8.0` project (`PublishSingleFile`, `SelfContained`, `win-x64`) |
| `bob/worker/dotnet/Program.cs` | `--version` / `--help` / `--selftest-spawn`; crash hook |
| `bob/worker/dotnet/AssertFresh.cs` | FR #9806: refuse `--resume` / `-r` / `--continue` / `-c` / session attach flags |
| `bob/worker/dotnet/GrokSpawn.cs` | FR #9806: build argv + spawn with creation flags 0 (inherit console; never `CREATE_NEW_CONSOLE`) |
| `bob/worker/dotnet/StartupProgress.cs` | Stop-before-spawn clear (full spinner UX is FR-C #9802) |
| `bob/worker/dotnet/GeneratedSourceCommit.cs` | Placeholder overwritten by the build script before publish |
| `bob/scripts/Build-BobWorkerNet.ps1` | Invokes `dotnet publish`; embeds source commit; restores placeholder |
| `.github/workflows/build-bob-worker-net.yml` | CI: setup-dotnet -> publish -> PE + `--version` + `--selftest-spawn` -> artifact |
| `bob/tests/test_fr9800_bob_worker_net_build_ci.py` | Phase 0 pins (dotnet not csc) |
| `bob/tests/test_fr9806_grok_spawn_one_console.py` | Phase 3 pins (assert_fresh + one console) |

## CLI

* `bob-worker-net.exe --version` - prints the embedded source commit SHA and exits **0**.
* `bob-worker-net.exe --help` - short usage; exits 0.
* `bob-worker-net.exe --selftest-spawn` - FR #9806: assert_fresh cases + spinner Stop + inherit-console `cmd /c exit 0` smoke; exits **0** on pass.
* Any other argv - stderr note that CLI/fuel/IRC land in later FRs; exits **64**.

Crash hook: `AppDomain.UnhandledException` writes a short line to stderr and, when `BOB_WORKER_RUN_DIR` is set, to `bob-worker-net-crash.txt` under that directory.

## FR #9806: Grok spawn always-new, one console

Parity with Python `bob_worker.assert_fresh` / `default_spawn` (t765u / t771u):

1. **assert_fresh** - `AssertFresh.Assert` refuses resume/continue/attach flags on argv and in launcher script bodies.
2. **New session** - `GrokSpawn.BuildArgv` uses `-s <uuid>` (never `--resume`).
3. **One window** - child process inherits the worker console (`creationFlags = 0`; no `CREATE_NEW_CONSOLE`, no `CREATE_NO_WINDOW`).
4. **Stop spinner before spawn** - `StartupProgress.Stop()` clears the startup line so the agent TUI owns the console.

## Build locally

```powershell
.\bob\scripts\Build-BobWorkerNet.ps1 -OutDir $env:TEMP\bob-worker-net-out -SourceCommit (git rev-parse HEAD)
$exe = "$env:TEMP\bob-worker-net-out\worker-net-publish\bob-worker-net.exe"
& $exe --version
& $exe --selftest-spawn
```

## Out of scope

FR-B #9801 CLI parity, FR-C #9802 full StartupProgress spinner UX, FR-H..J inject/Cursor/OpenCode spawn, fuel/IRC, MSI, retiring PyInstaller worker. No interim Python fuel speedups.

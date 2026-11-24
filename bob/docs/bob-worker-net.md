# bob-worker-net (.NET 8 Phase 0 scaffold, FR #9800)

Phase 0 of digest **#9794** / epic **#9793**: a console host compiled with the **.NET 8 SDK**, not the in-box Framework 4 `csc.exe` used by tray dialogs.

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
| `bob/worker/dotnet/Program.cs` | `--version` / `--help` / usage exit 64; unhandled-exception crash hook |
| `bob/worker/dotnet/GeneratedSourceCommit.cs` | Placeholder overwritten by the build script before publish |
| `bob/scripts/Build-BobWorkerNet.ps1` | Invokes `dotnet publish`; embeds source commit; restores placeholder |
| `.github/workflows/build-bob-worker-net.yml` | CI: setup-dotnet → publish → PE + `--version` check → artifact `bob-worker-net` |
| `bob/tests/test_fr9800_bob_worker_net_build_ci.py` | Source pins (dotnet not csc; workflow + docs) |

## CLI (Phase 0)

* `bob-worker-net.exe --version` — prints the embedded source commit SHA and exits **0**.
* `bob-worker-net.exe --help` — short usage; exits 0.
* Any other argv — stderr note that CLI/fuel/IRC land in later FRs; exits **64**.

Crash hook: `AppDomain.UnhandledException` writes a short line to stderr and, when `BOB_WORKER_RUN_DIR` is set, to `bob-worker-net-crash.txt` under that directory.

## Build locally

```powershell
.\bob\scripts\Build-BobWorkerNet.ps1 -OutDir $env:TEMP\bob-worker-net-out -SourceCommit (git rev-parse HEAD)
& "$env:TEMP\bob-worker-net-out\worker-net-publish\bob-worker-net.exe" --version
```

## Out of scope for FR #9800

CLI surface parity (FR-B #9801), StartupProgress spinner (FR-C #9802), seat fuel/IRC, MSI packaging, and replacing the Python `bob-worker.exe` are later work under the epic. No interim Python fuel speedups in this FR.

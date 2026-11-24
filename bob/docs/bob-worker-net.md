# bob-worker-net (.NET 8 scaffold + IrcSeat, FR #9800 / #9804)

Phase 0–1 of digest **#9794** / epic **#9793**: a console host compiled with the **.NET 8 SDK**, not the in-box Framework 4 `csc.exe` used by tray dialogs. FR **#9804** adds TLS IRC (`IrcSeat`) with a fail-closed JOIN gate before any future agent spawn.

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
| `bob/worker/dotnet/Program.cs` | `--version` / `--help` / `--self-test-irc`; usage exit 64; crash hook |
| `bob/worker/dotnet/IrcSeat.cs` | PASS/NICK/USER → 001 → JOIN `#machine`; `CanStartAgent` / `StartAgentGate` |
| `bob/worker/dotnet/SslStreamIrcTransport.cs` | Production `TcpClient` + `SslStream` TLS transport |
| `bob/worker/dotnet/FakeIrcTransport.cs` | In-memory transport for hermetic CI / `--self-test-irc` |
| `bob/worker/dotnet/IIrcTransport.cs` | Injectable byte transport |
| `bob/worker/dotnet/ErgoPassword.cs` | Same search paths as Python `find_ergo_password` (never log secret) |
| `bob/worker/dotnet/GeneratedSourceCommit.cs` | Placeholder overwritten by the build script before publish |
| `bob/scripts/Build-BobWorkerNet.ps1` | Invokes `dotnet publish`; embeds source commit; restores placeholder |
| `.github/workflows/build-bob-worker-net.yml` | CI: setup-dotnet → publish → PE + `--version` + `--self-test-irc` → artifact |
| `bob/tests/test_fr9800_bob_worker_net_build_ci.py` | Source pins (dotnet not csc; workflow + docs) |
| `bob/tests/test_fr9804_irc_seat_join_gate.py` | Source pins for IrcSeat JOIN gate, SslStream, Ergo paths, CI self-test |

## CLI

* `bob-worker-net.exe --version` — prints the embedded source commit SHA and exits **0**.
* `bob-worker-net.exe --help` — short usage; exits 0.
* `bob-worker-net.exe --self-test-irc` — hermetic mock contract (FR #9804): JOIN required before `StartAgentGate` opens; Ergo path candidates; never needs live Ergo. Exit **0** on pass, **1** on failure.
* Any other argv — stderr note that full CLI/fuel/spawn land in later FRs; exits **64**.

Crash hook: `AppDomain.UnhandledException` writes a short line to stderr and, when `BOB_WORKER_RUN_DIR` is set, to `bob-worker-net-crash.txt` under that directory.

## IrcSeat JOIN gate (FR #9804)

* Connect order: optional `PASS` (Ergo secret) → `NICK`/`USER` → wait `001` → `JOIN #machine` → confirm own JOIN.
* `IrcSeat.CanStartAgent` / `StartAgentGate.IsOpen` stay **false** until registered **and** joined; `EnsureOpen` throws if spawn is attempted early.
* `ConnectWithRetries` mirrors Python `connect_with_retries` (backoff then fail-closed).
* Ergo PASS from `BOB_IRC_PASSWORD` or the same on-disk candidates as Python (`install/home|config/ergo.password`, `%USERPROFILE%\.bobiverse\ergo.password`, `.grok\ergo\connect.password` / `ergo.password`). Never log the secret value.
* Production transport is `SslStreamIrcTransport` (TLS to `irc.ntsa.uk:6697` by default). Tests inject `FakeIrcTransport`.

## Build locally

```powershell
.\bob\scripts\Build-BobWorkerNet.ps1 -OutDir $env:TEMP\bob-worker-net-out -SourceCommit (git rev-parse HEAD)
$exe = "$env:TEMP\bob-worker-net-out\worker-net-publish\bob-worker-net.exe"
& $exe --version
& $exe --self-test-irc
```

## Out of scope

CLI surface parity (FR-B #9801), StartupProgress spinner (FR-C #9802), live seat fuel/spawn wiring, MSI packaging, and replacing the Python `bob-worker.exe` are later work under the epic. No interim Python fuel speedups in this FR.

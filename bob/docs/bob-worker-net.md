# bob-worker-net (.NET 8, FR #9800 / #9804 / #9806)

Phase 0 scaffold (digest **#9794**) plus FR-E IrcSeat JOIN gate (digest **#9796**) and Phase 3 Grok spawn (digest **#9797** / epic **#9793**): a console host compiled with the **.NET 8 SDK**, not the in-box Framework 4 `csc.exe` used by tray dialogs. Airc min-spec / no-SDK does **not** apply.

## Layout

| Path | Role |
| --- | --- |
| `bob/worker/dotnet/BobWorkerNet.csproj` | SDK-style `net8.0`, self-contained win-x64 publish |
| `bob/worker/dotnet/Program.cs` | `--version` / `--help` / `--self-test-irc` / `--selftest-spawn`; usage exit 64; crash hook |
| `bob/worker/dotnet/IrcSeat.cs` | PASS/NICK/USER -> 001 -> JOIN `#machine`; `CanStartAgent` / `StartAgentGate` |
| `bob/worker/dotnet/SslStreamIrcTransport.cs` | Production `TcpClient` + `SslStream` TLS transport |
| `bob/worker/dotnet/FakeIrcTransport.cs` | In-memory transport for hermetic CI / `--self-test-irc` |
| `bob/worker/dotnet/IIrcTransport.cs` | Injectable byte transport |
| `bob/worker/dotnet/ErgoPassword.cs` | Same search paths as Python `find_ergo_password` (never log secret) |
| `bob/worker/dotnet/AssertFresh.cs` | FR #9806: refuse `--resume` / `-r` / `--continue` / `-c` / session attach flags |
| `bob/worker/dotnet/GrokSpawn.cs` | FR #9806: build argv + spawn with creation flags 0 (inherit console; never `CREATE_NEW_CONSOLE`) |
| `bob/worker/dotnet/StartupProgress.cs` | Stop-before-spawn clear (full spinner UX is FR-C #9802) |
| `bob/worker/dotnet/GeneratedSourceCommit.cs` | Placeholder overwritten by the build script before publish |
| `bob/scripts/Build-BobWorkerNet.ps1` | Invokes `dotnet publish`; embeds source commit; restores placeholder |
| `.github/workflows/build-bob-worker-net.yml` | CI: setup-dotnet -> publish -> PE + `--version` + `--self-test-irc` + `--selftest-spawn` -> artifact |
| `bob/tests/test_fr9800_bob_worker_net_build_ci.py` | Phase 0 pins (dotnet not csc) |
| `bob/tests/test_fr9804_irc_seat_join_gate.py` | Source pins for IrcSeat JOIN gate, SslStream, Ergo paths, CI self-test |
| `bob/tests/test_fr9806_grok_spawn_one_console.py` | Phase 3 pins (assert_fresh + one console) |

## CLI

* `bob-worker-net.exe --version` - prints the embedded source commit SHA and exits **0**.
* `bob-worker-net.exe --help` - short usage; exits 0.
* `bob-worker-net.exe --self-test-irc` - hermetic mock contract (FR #9804): JOIN required before `StartAgentGate` opens; Ergo path candidates; never needs live Ergo.
* `bob-worker-net.exe --selftest-spawn` - FR #9806: assert_fresh cases + spinner Stop + inherit-console `cmd /c exit 0` smoke; exits **0** on pass.
* Any other argv - stderr note that remaining CLI/fuel land in later FRs; exits **64**.

Crash hook: `AppDomain.UnhandledException` writes a short line to stderr and, when `BOB_WORKER_RUN_DIR` is set, to `bob-worker-net-crash.txt` under that directory.

## IrcSeat JOIN gate (FR #9804)

* Connect order: optional `PASS` (Ergo secret) -> `NICK`/`USER` -> wait `001` -> `JOIN #machine` -> confirm own JOIN.
* `IrcSeat.CanStartAgent` / `StartAgentGate.IsOpen` stay **false** until registered **and** joined; `EnsureOpen` throws if spawn is attempted early.
* `ConnectWithRetries` mirrors Python `connect_with_retries` (backoff then fail-closed).
* Ergo PASS from `BOB_IRC_PASSWORD` or the same on-disk candidates as Python (`install/home|config/ergo.password`, `%USERPROFILE%\.bobiverse\ergo.password`, `.grok/ergo/connect.password`).
* Production transport is `SslStreamIrcTransport` (TLS to `irc.ntsa.uk:6697` by default). Tests inject `FakeIrcTransport`.

## FR #9806: Grok spawn always-new, one console

Parity with Python `bob_worker.assert_fresh` / `default_spawn` (t765u / t771u):

1. **assert_fresh** - `AssertFresh.Assert` refuses resume/continue/attach flags on argv and in launcher script bodies.
2. **New session** - `GrokSpawn.BuildArgv` uses `-s <uuid>` (never `--resume`).
3. **One window** - child process inherits the worker console (`creationFlags = 0`; no `CREATE_NEW_CONSOLE`, no `CREATE_NO_WINDOW`).
4. **Stop spinner before spawn** - `StartupProgress.Stop()` clears the startup line so the agent TUI owns the console.

## Local build

```powershell
& bob/scripts/Build-BobWorkerNet.ps1
& bob/worker/dotnet/bin/Release/net8.0/win-x64/publish/bob-worker-net.exe --version
& bob/worker/dotnet/bin/Release/net8.0/win-x64/publish/bob-worker-net.exe --self-test-irc
& bob/worker/dotnet/bin/Release/net8.0/win-x64/publish/bob-worker-net.exe --selftest-spawn
```

## Out of scope

FR-B #9801 CLI parity, FR-C #9802 full StartupProgress spinner UX, FR-H..J inject/Cursor/OpenCode spawn, fuel wiring, MSI, retiring PyInstaller worker.

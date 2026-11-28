// FR #9800: Phase 0 .NET 8 bob-worker console scaffold.
// FR #9804: IrcSeat TLS + JOIN gate self-test (--self-test-irc).
// FR #9806: Grok spawn always-new one console (--selftest-spawn).
namespace Bobiverse.WorkerNet;

internal static class Program
{
    // Build-BobWorkerNet.ps1 writes GeneratedSourceCommit.cs before publish.
    internal static string SourceCommit =>
        GeneratedSourceCommit.Value
        ?? Environment.GetEnvironmentVariable("BOB_WORKER_NET_SOURCE_COMMIT")
        ?? "unknown";

    private static int Main(string[] args)
    {
        InstallCrashHook();

        if (!CliArgs.TryParse(args, out var cli, out var parseError))
        {
            Console.Error.WriteLine("bob-worker-net: " + parseError);
            return 64;
        }

        if (cli.Version)
        {
            Console.Out.WriteLine(SourceCommit);
            return 0;
        }

        if (cli.Help)
        {
            Console.Out.WriteLine("bob-worker-net (.NET 8, FR #9800 / #9801 / #9804 / #9806)");
            Console.Out.WriteLine("Dual-build name bob-worker-net.exe until cutover (FR #9801).");
            Console.Out.WriteLine("  --version         print embedded source commit and exit 0");
            Console.Out.WriteLine("  --help            this text");
            Console.Out.WriteLine("  --mode            agent | plan | monitor | maintenance | jeeves");
            Console.Out.WriteLine("  --install-root    bob install root");
            Console.Out.WriteLine("  --machine-id      shop machine id");
            Console.Out.WriteLine("  --agent           grok | cursor | opencode");
            Console.Out.WriteLine("  --list-agents     JSON agent rows and exit 0 (stub, starts nothing)");
            Console.Out.WriteLine("  --dry-run         JSON selection and exit 0 (stub, starts nothing)");
            Console.Out.WriteLine("  --echo            accepted; dry-run echoes the flag");
            Console.Out.WriteLine("  --self-test-irc   hermetic IrcSeat JOIN gate tests (no live Ergo)");
            Console.Out.WriteLine("  --selftest-spawn  FR #9806 assert_fresh + one-console spawn smoke");
            return 0;
        }

        if (cli.SelfTestIrc)
        {
            return RunIrcSelfTest();
        }

        if (cli.SelftestSpawn)
        {
            return RunSelftestSpawn();
        }

        if (cli.ListAgents)
        {
            Console.Out.WriteLine(CliArgs.ListAgentsJson());
            return 0;
        }

        if (cli.DryRun)
        {
            Console.Out.WriteLine(CliArgs.DryRunJson(cli));
            return 0;
        }

        Console.Error.WriteLine(
            "bob-worker-net: parsed mode " + cli.Mode +
            " (FR #9801). Seat loop is a later phase. Exits 64.");
        return 64;
    }

    /// <summary>FR #9806 CI smoke: assert_fresh + inherit-console child (cmd.exe).</summary>
    private static int RunSelftestSpawn()
    {
        var failures = 0;

        void Check(string name, bool ok, string detail = "")
        {
            if (ok)
            {
                Console.Out.WriteLine("ok " + name);
            }
            else
            {
                failures++;
                Console.Error.WriteLine("FAIL " + name + (detail.Length > 0 ? ": " + detail : ""));
            }
        }

        // --- assert_fresh ---
        try
        {
            AssertFresh.Assert(new[] { "agent.exe", "-s", Guid.NewGuid().ToString("D") });
            Check("assert_fresh_ok_argv", true);
        }
        catch (Exception ex)
        {
            Check("assert_fresh_ok_argv", false, ex.Message);
        }

        foreach (var bad in new[]
                 {
                     new[] { "agent.exe", "--resume", "x" },
                     new[] { "agent.exe", "-r", "sid" },
                     new[] { "agent.exe", "--continue" },
                     new[] { "agent.exe", "-c" },
                     new[] { "agent.exe", "--session", "x" },
                     new[] { "agent.exe", "--chat" },
                 })
        {
            var name = "assert_fresh_refuse_" + bad[1].TrimStart('-');
            try
            {
                AssertFresh.Assert(bad);
                Check(name, false, "expected refuse");
            }
            catch (InvalidOperationException)
            {
                Check(name, true);
            }
            catch (Exception ex)
            {
                Check(name, false, ex.Message);
            }
        }

        try
        {
            AssertFresh.Assert(
                new[] { "powershell.exe", "-File", "launch.ps1" },
                new Dictionary<string, string> { ["launch.ps1"] = "& agent --resume abc" });
            Check("assert_fresh_refuse_script", false, "expected refuse");
        }
        catch (InvalidOperationException)
        {
            Check("assert_fresh_refuse_script", true);
        }

        // --- BuildArgv never emits forbidden flags ---
        var sid = Guid.NewGuid().ToString("D");
        var cwd = Environment.CurrentDirectory;
        var spec = new GrokLaunchSpec
        {
            Exe = "agent.exe",
            Cwd = cwd,
            SessionId = sid,
            Prompt = "ping",
        };
        List<string> argv;
        try
        {
            argv = GrokSpawn.BuildArgv(spec);
            Check("build_argv_fresh", !argv.Any(a => AssertFresh.ForbiddenFlags.Contains(a, StringComparer.OrdinalIgnoreCase)));
            Check("build_argv_session", argv.Contains("-s") && argv.Contains(sid));
        }
        catch (Exception ex)
        {
            Check("build_argv_fresh", false, ex.Message);
            argv = new List<string>();
        }

        // --- spinner Stop before spawn ---
        var sw = new StringWriter();
        using (var progress = new StartupProgress(sw))
        {
            progress.Start("spawn-ready");
            Check("spinner_active", progress.IsActive);
            progress.Stop();
            Check("spinner_stopped", !progress.IsActive);
            Check("spinner_cleared", sw.ToString().Contains('\r'));
        }

        // --- one-console child: cmd.exe inherits (creation flags 0) ---
        if (!OperatingSystem.IsWindows())
        {
            Check("spawn_windows_only", true, "skipped non-windows");
            return failures == 0 ? 0 : 1;
        }

        var comspec = Environment.GetEnvironmentVariable("ComSpec") ?? @"C:\Windows\System32\cmd.exe";
        if (!File.Exists(comspec))
        {
            Check("spawn_comspec", false, "missing " + comspec);
            return 1;
        }

        // GrokSpawn.Start must Stop() spinner even when the exe path is missing.
        using (var progressFail = new StartupProgress(TextWriter.Null))
        {
            progressFail.Start("pre-spawn");
            try
            {
                GrokSpawn.Start(
                    new GrokLaunchSpec
                    {
                        Exe = Path.Combine(cwd, "no-such-agent-9806.exe"),
                        Cwd = cwd,
                        SessionId = sid,
                    },
                    progressFail);
                Check("spawn_missing_exe", false, "expected start failure");
            }
            catch
            {
                Check("spawn_missing_exe_stopped_spinner", !progressFail.IsActive);
            }
        }

        // Inherit-console child (cmd /c exit 0). Creation flags stay 0.
        var smoke = InheritConsoleSmoke(comspec, cwd);
        Check("spawn_creation_flags_zero", smoke.CreationFlags == 0);
        Check("spawn_no_new_console", (smoke.CreationFlags & WinCreateFlags.CREATE_NEW_CONSOLE) == 0);
        Check("spawn_child_exited_0", smoke.ExitCode == 0, "exit=" + smoke.ExitCode);
        if (smoke.ConsoleShareKnown)
        {
            Check("spawn_console_share", smoke.SharedConsole, smoke.Detail);
        }
        else
        {
            Console.Out.WriteLine("ok spawn_console_share_skipped " + smoke.Detail);
        }

        return failures == 0 ? 0 : 1;
    }

    private sealed class SmokeResult
    {
        internal uint CreationFlags;
        internal int ExitCode = -1;
        internal bool ConsoleShareKnown;
        internal bool SharedConsole;
        internal string Detail = "";
    }

    /// <summary>Spawn cmd /c exit 0 with creation flags 0; optional GetConsoleProcessList share check.</summary>
    private static SmokeResult InheritConsoleSmoke(string comspec, string cwd)
    {
        var result = new SmokeResult { CreationFlags = 0 };
        var psi = new System.Diagnostics.ProcessStartInfo
        {
            FileName = comspec,
            ArgumentList = { "/d", "/c", "exit", "0" },
            WorkingDirectory = cwd,
            UseShellExecute = false,
            RedirectStandardInput = false,
            RedirectStandardOutput = false,
            RedirectStandardError = false,
            CreateNoWindow = false,
        };

        using var proc = System.Diagnostics.Process.Start(psi)
                         ?? throw new InvalidOperationException("smoke Process.Start null");
        result.CreationFlags = 0;
        if (!proc.WaitForExit(15000))
        {
            try { proc.Kill(entireProcessTree: true); } catch { /* ignore */ }
            result.Detail = "timeout";
            return result;
        }

        result.ExitCode = proc.ExitCode;

        // Best-effort: if we have a console, parent should still be listed after child exit.
        try
        {
            var k32 = NativeConsole.GetConsoleProcessList;
            if (k32 is not null)
            {
                var buf = new uint[16];
                var n = k32(buf, (uint)buf.Length);
                result.ConsoleShareKnown = true;
                result.SharedConsole = n >= 1 && buf.Take((int)n).Contains((uint)Environment.ProcessId);
                result.Detail = "n=" + n + " me=" + Environment.ProcessId;
            }
            else
            {
                result.Detail = "no GetConsoleProcessList";
            }
        }
        catch (Exception ex)
        {
            result.Detail = ex.GetType().Name;
        }

        return result;
    }

    private static class NativeConsole
    {
        [System.Runtime.InteropServices.DllImport(
            "kernel32.dll",
            SetLastError = true,
            EntryPoint = "GetConsoleProcessList")]
        private static extern uint GetConsoleProcessListNative(uint[] list, uint count);

        internal static Func<uint[], uint, uint>? GetConsoleProcessList { get; } =
            OperatingSystem.IsWindows()
                ? static (list, count) => GetConsoleProcessListNative(list, count)
                : null;
    }

    /// <summary>FR #9804: mock contract — JOIN required before start_agent; retries; Ergo paths.</summary>
    internal static int RunIrcSelfTest()
    {
        var failures = 0;
        void Check(string name, bool ok)
        {
            if (ok)
            {
                Console.Out.WriteLine("PASS " + name);
            }
            else
            {
                Console.Error.WriteLine("FAIL " + name);
                failures++;
            }
        }

        // 1) Happy path: 001 + JOIN => CanStartAgent / StartAgentGate open.
        {
            var fake = new FakeIrcTransport();
            fake.ArmWelcome("flamingo-1", "#flamingo");
            using var seat = new IrcSeat(
                "flamingo-1", "flamingo", password: "secret-not-logged",
                transport: fake, log: _ => { });
            Check("gate closed before connect", !StartAgentGate.IsOpen(seat));
            seat.ConnectWithRetries(attempts: 1, timeout: TimeSpan.FromSeconds(5), backoffSeconds: new[] { 0.0 });
            Check("registered", seat.IsRegistered);
            Check("joined", seat.IsJoined);
            Check("CanStartAgent", seat.CanStartAgent);
            Check("StartAgentGate open", StartAgentGate.IsOpen(seat));
            var sent = string.Join('\n', fake.Sent);
            var passAt = sent.IndexOf("PASS ", StringComparison.Ordinal);
            var nickAt = sent.IndexOf("NICK ", StringComparison.Ordinal);
            Check("sent PASS before NICK", passAt >= 0 && nickAt > passAt);
            Check("sent JOIN shop", fake.Sent.Any(l => l.Equals("JOIN #flamingo", StringComparison.OrdinalIgnoreCase)));
            var seatText = seat.ToString() ?? "";
            Check("password not logged via ToString", !seatText.Contains("secret-not-logged", StringComparison.Ordinal));
        }

        // 2) Fail closed: no JOIN => gate stays closed.
        {
            var fake = new FakeIrcTransport();
            fake.EnqueueServerLine(":ergo.example 001 flamingo-2 :Welcome");
            // no JOIN echo
            using var seat = new IrcSeat("flamingo-2", "flamingo", transport: fake, log: _ => { });
            var threw = false;
            try
            {
                seat.Connect(TimeSpan.FromMilliseconds(200));
            }
            catch (Exception)
            {
                threw = true;
            }

            Check("no-JOIN throws", threw);
            Check("no-JOIN gate closed", !StartAgentGate.IsOpen(seat));
            try
            {
                StartAgentGate.EnsureOpen(seat);
                Check("EnsureOpen throws", false);
            }
            catch (InvalidOperationException)
            {
                Check("EnsureOpen throws", true);
            }
        }

        // 3) Ergo password search paths (env wins; never require printing secret).
        {
            var tmp = Path.Combine(Path.GetTempPath(), "bob-worker-net-ergo-" + Guid.NewGuid().ToString("n"));
            Directory.CreateDirectory(Path.Combine(tmp, "home"));
            var secret = "unit-test-pass-" + Guid.NewGuid().ToString("n");
            File.WriteAllText(Path.Combine(tmp, "home", "ergo.password"), secret);
            var found = ErgoPassword.Find(tmp, new Dictionary<string, string>());
            Check("find ergo.password under install home", found == secret);
            var envWin = ErgoPassword.Find(tmp, new Dictionary<string, string>
            {
                ["BOB_IRC_PASSWORD"] = "from-env",
            });
            Check("BOB_IRC_PASSWORD wins", envWin == "from-env");
            var paths = string.Join('|', ErgoPassword.CandidatePaths(tmp, @"C:\Users\example"));
            Check("candidate paths include home+config+.bobiverse+.grok",
                paths.Contains("home" + Path.DirectorySeparatorChar + "ergo.password", StringComparison.Ordinal)
                && paths.Contains("config" + Path.DirectorySeparatorChar + "ergo.password", StringComparison.Ordinal)
                && paths.Contains(".bobiverse", StringComparison.Ordinal)
                && paths.Contains(Path.Combine(".grok", "ergo", "connect.password"), StringComparison.Ordinal));
            try { Directory.Delete(tmp, recursive: true); } catch { /* ignore */ }
        }

        if (failures == 0)
        {
            Console.Out.WriteLine("bob-worker-net --self-test-irc: all passed");
            return 0;
        }

        Console.Error.WriteLine($"bob-worker-net --self-test-irc: {failures} failure(s)");
        return 1;
    }

    /// <summary>FR #9800: unhandled exception hook (parity with Python crash_report.install).</summary>
    internal static void InstallCrashHook()
    {
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            try
            {
                var ex = e.ExceptionObject as Exception;
                var msg = ex?.GetType().Name + ": " + (ex?.Message ?? e.ExceptionObject?.ToString() ?? "?");
                if (msg.Length > 400)
                {
                    msg = msg[..400];
                }

                Console.Error.WriteLine("bob-worker-net crash: " + msg);
                var run = Environment.GetEnvironmentVariable("BOB_WORKER_RUN_DIR");
                if (!string.IsNullOrWhiteSpace(run))
                {
                    Directory.CreateDirectory(run);
                    File.WriteAllText(
                        Path.Combine(run, "bob-worker-net-crash.txt"),
                        DateTime.UtcNow.ToString("o") + " " + msg + Environment.NewLine);
                }
            }
            catch
            {
                // never throw from the crash hook
            }
        };
    }
}

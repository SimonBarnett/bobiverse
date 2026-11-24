// FR #9800: Phase 0 .NET 8 bob-worker console scaffold.
// FR #9804: IrcSeat TLS + JOIN gate self-test (--self-test-irc).
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

        if (args.Any(a => string.Equals(a, "--version", StringComparison.OrdinalIgnoreCase)))
        {
            Console.Out.WriteLine(SourceCommit);
            return 0;
        }

        if (args.Any(a => string.Equals(a, "--help", StringComparison.OrdinalIgnoreCase)
                       || string.Equals(a, "-h", StringComparison.OrdinalIgnoreCase)))
        {
            Console.Out.WriteLine("bob-worker-net (.NET 8, FR #9800 / #9804)");
            Console.Out.WriteLine("  --version        print embedded source commit and exit 0");
            Console.Out.WriteLine("  --help           this text");
            Console.Out.WriteLine("  --self-test-irc  hermetic IrcSeat JOIN gate tests (no live Ergo)");
            return 0;
        }

        if (args.Any(a => string.Equals(a, "--self-test-irc", StringComparison.OrdinalIgnoreCase)))
        {
            return RunIrcSelfTest();
        }

        Console.Error.WriteLine(
            "bob-worker-net: host scaffold (FR #9800) + IrcSeat (FR #9804). " +
            "Full CLI / fuel / spawn land in later FRs. Use --self-test-irc for JOIN gate.");
        return 64;
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

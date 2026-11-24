// FR #9800: Phase 0 .NET 8 bob-worker console scaffold.
// Crash hook + --version only; CLI/fuel/IRC land in later phase FRs.
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
            Console.Out.WriteLine("bob-worker-net (.NET 8 scaffold, FR #9800)");
            Console.Out.WriteLine("  --version   print embedded source commit and exit 0");
            Console.Out.WriteLine("  --help      this text");
            return 0;
        }

        Console.Error.WriteLine(
            "bob-worker-net: Phase 0 scaffold only (FR #9800). " +
            "CLI / fuel / IRC land in later FRs under digest #9794.");
        return 64;
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

// FR #9806: Grok agent.exe always-new, one console (inherit; never CREATE_NEW_CONSOLE).
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Bobiverse.WorkerNet;

internal static class WinCreateFlags
{
    internal const uint CREATE_NEW_CONSOLE = 0x00000010;
    internal const uint CREATE_NO_WINDOW = 0x08000000;
}

internal sealed class GrokLaunchSpec
{
    internal required string Exe { get; init; }
    internal required string Cwd { get; init; }
    internal required string SessionId { get; init; }
    internal string Prompt { get; init; } = "";
    internal IReadOnlyList<string>? ExtraArgs { get; init; }
    internal IReadOnlyDictionary<string, string>? ScriptFiles { get; init; }
}

internal sealed class SpawnedAgent : IDisposable
{
    internal required Process Process { get; init; }
    internal required uint CreationFlags { get; init; }
    internal required string SessionId { get; init; }
    internal IReadOnlyList<string> Argv { get; init; } = Array.Empty<string>();

    public void Dispose()
    {
        try
        {
            if (!Process.HasExited)
            {
                Process.Kill(entireProcessTree: true);
            }
        }
        catch
        {
            // best-effort
        }

        Process.Dispose();
    }
}

internal static class GrokSpawn
{
    /// <summary>Build agent.exe argv: new session id, no resume/continue flags.</summary>
    internal static List<string> BuildArgv(GrokLaunchSpec spec)
    {
        var argv = new List<string>
        {
            spec.Exe,
            "--no-auto-update",
            "--no-alt-screen",
            "--cwd",
            spec.Cwd,
            "--disallowed-tools",
            "ask_user_question",
            "-s",
            spec.SessionId,
        };
        if (spec.ExtraArgs is { Count: > 0 })
        {
            argv.AddRange(spec.ExtraArgs);
        }

        if (!string.IsNullOrEmpty(spec.Prompt))
        {
            argv.Add(spec.Prompt);
        }

        AssertFresh.Assert(argv, spec.ScriptFiles);
        return argv;
    }

    /// <summary>
    /// Stop spinner, then start agent as a console child that inherits this process console.
    /// Creation flags are 0 (no CREATE_NEW_CONSOLE, no CREATE_NO_WINDOW) - t771u one window.
    /// </summary>
    internal static SpawnedAgent Start(GrokLaunchSpec spec, StartupProgress? progress = null)
    {
        var argv = BuildArgv(spec);
        progress?.Stop();

        const uint creationFlags = 0;
        if ((creationFlags & WinCreateFlags.CREATE_NEW_CONSOLE) != 0
            || (creationFlags & WinCreateFlags.CREATE_NO_WINDOW) != 0)
        {
            throw new InvalidOperationException("FR #9806: agent must inherit the worker console");
        }

        var psi = new ProcessStartInfo
        {
            FileName = argv[0],
            WorkingDirectory = spec.Cwd,
            UseShellExecute = false,
            // Inherit stdin/stdout/stderr so the agent shares our console (one window).
            RedirectStandardInput = false,
            RedirectStandardOutput = false,
            RedirectStandardError = false,
            CreateNoWindow = false,
        };
        for (var i = 1; i < argv.Count; i++)
        {
            psi.ArgumentList.Add(argv[i]);
        }

        Process proc;
        if (OperatingSystem.IsWindows() && string.Equals(
                Environment.GetEnvironmentVariable("BOB_WORKER_NET_SPAWN_CREATEPROCESS"),
                "1",
                StringComparison.Ordinal))
        {
            // Optional CreateProcess path for explicit dwCreationFlags=0 (CI selftest).
            proc = StartCreateProcess(argv, spec.Cwd, creationFlags);
        }
        else
        {
            proc = Process.Start(psi)
                   ?? throw new InvalidOperationException("Process.Start returned null for " + argv[0]);
        }

        return new SpawnedAgent
        {
            Process = proc,
            CreationFlags = creationFlags,
            SessionId = spec.SessionId,
            Argv = argv,
        };
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern bool CreateProcessW(
        string? lpApplicationName,
        string lpCommandLine,
        IntPtr lpProcessAttributes,
        IntPtr lpThreadAttributes,
        bool bInheritHandles,
        uint dwCreationFlags,
        IntPtr lpEnvironment,
        string? lpCurrentDirectory,
        ref STARTUPINFO lpStartupInfo,
        out PROCESS_INFORMATION lpProcessInformation);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct STARTUPINFO
    {
        public int cb;
        public string? lpReserved;
        public string? lpDesktop;
        public string? lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute;
        public int dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PROCESS_INFORMATION
    {
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }

    private static Process StartCreateProcess(IReadOnlyList<string> argv, string cwd, uint flags)
    {
        var cmd = QuoteArgv(argv);
        var si = new STARTUPINFO { cb = Marshal.SizeOf<STARTUPINFO>() };
        if (!CreateProcessW(
                null,
                cmd,
                IntPtr.Zero,
                IntPtr.Zero,
                bInheritHandles: true,
                dwCreationFlags: flags,
                lpEnvironment: IntPtr.Zero,
                lpCurrentDirectory: cwd,
                ref si,
                out var pi))
        {
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        }

        try
        {
            return Process.GetProcessById(pi.dwProcessId);
        }
        finally
        {
            if (pi.hThread != IntPtr.Zero)
            {
                CloseHandle(pi.hThread);
            }

            if (pi.hProcess != IntPtr.Zero)
            {
                CloseHandle(pi.hProcess);
            }
        }
    }

    internal static string QuoteArgv(IReadOnlyList<string> argv)
    {
        return string.Join(" ", argv.Select(QuoteOne));
    }

    private static string QuoteOne(string arg)
    {
        if (arg.Length == 0)
        {
            return "\"\"";
        }

        if (arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
        {
            return arg;
        }

        return "\"" + arg.Replace("\"", "\\\"") + "\"";
    }
}

// FR #9801: tray-compatible argv. Stubs only; the seat loop is a later phase.
namespace Bobiverse.WorkerNet;

internal sealed class CliArgs
{
    internal const int UsageExit = 64;

    internal static readonly string[] Modes = { "agent", "plan", "monitor", "maintenance", "jeeves" };
    internal static readonly string[] Agents = { "", "grok", "cursor", "opencode" };

    internal string Mode { get; private set; } = "agent";
    internal string InstallRoot { get; private set; } = "";
    internal string MachineId { get; private set; } = "";
    internal string Agent { get; private set; } = "";
    internal bool ListAgents { get; private set; }
    internal bool DryRun { get; private set; }
    internal bool Echo { get; private set; }
    internal bool Version { get; private set; }
    internal bool Help { get; private set; }
    internal bool SelfTestIrc { get; private set; }
    internal bool SelftestSpawn { get; private set; }

    internal static bool TryParse(string[] args, out CliArgs cli, out string error)
    {
        cli = new CliArgs();
        error = "";
        for (var i = 0; i < args.Length; i++)
        {
            var a = args[i] ?? "";
            if (Is(a, "--mode"))
            {
                if (!Take(args, ref i, out var value))
                {
                    error = "unknown mode ''";
                    return false;
                }

                if (!Modes.Contains(value, StringComparer.OrdinalIgnoreCase))
                {
                    error = "unknown mode '" + value + "'";
                    return false;
                }

                cli.Mode = value.ToLowerInvariant();
                continue;
            }

            if (Is(a, "--install-root"))
            {
                if (!Take(args, ref i, out var value))
                {
                    error = "--install-root needs a value";
                    return false;
                }

                cli.InstallRoot = value;
                continue;
            }

            if (Is(a, "--machine-id"))
            {
                if (!Take(args, ref i, out var value))
                {
                    error = "--machine-id needs a value";
                    return false;
                }

                cli.MachineId = value;
                continue;
            }

            if (Is(a, "--agent"))
            {
                if (!Take(args, ref i, out var value))
                {
                    error = "unknown agent ''";
                    return false;
                }

                var agent = value.Trim().ToLowerInvariant();
                if (!Agents.Contains(agent, StringComparer.Ordinal))
                {
                    error = "unknown agent '" + value + "'";
                    return false;
                }

                cli.Agent = agent;
                continue;
            }

            if (Is(a, "--list-agents")) { cli.ListAgents = true; continue; }
            if (Is(a, "--dry-run")) { cli.DryRun = true; continue; }
            if (Is(a, "--echo")) { cli.Echo = true; continue; }
            if (Is(a, "--version")) { cli.Version = true; continue; }
            if (Is(a, "--help") || Is(a, "-h")) { cli.Help = true; continue; }
            if (Is(a, "--self-test-irc")) { cli.SelfTestIrc = true; continue; }
            if (Is(a, "--selftest-spawn")) { cli.SelftestSpawn = true; continue; }

            error = "unknown argument '" + a + "'";
            return false;
        }

        return true;
    }

    /// <summary>
    /// Stub list. Fuel is not read. Shape matches the tray parser: agents[] with
    /// id, label, available, installed, fuel_state, reason, plus refresh.
    /// </summary>
    internal static string ListAgentsJson()
    {
        return "{"
            + "\"agents\":["
            + Row("auto", "Automatic", true, true, "unknown", "Grok, then Cursor, then OpenCode") + ","
            + Row("grok", "Grok", false, false, "unknown", "not installed") + ","
            + Row("cursor", "Cursor", false, false, "unknown", "not installed") + ","
            + Row("opencode", "Open Code", false, false, "unknown", "not installed")
            + "],\"refresh\":false,\"stub\":true}";
    }

    internal static string DryRunJson(CliArgs cli)
    {
        return "{"
            + "\"agent\":\"" + Esc(cli.Agent) + "\","
            + "\"echo\":" + (cli.Echo ? "true" : "false") + ","
            + "\"install_root\":\"" + Esc(cli.InstallRoot) + "\","
            + "\"machine_id\":\"" + Esc(cli.MachineId) + "\","
            + "\"mode\":\"" + Esc(cli.Mode) + "\","
            + "\"started\":false,"
            + "\"stub\":true}";
    }

    private static string Row(string id, string label, bool available, bool installed, string fuel, string reason)
    {
        return "{"
            + "\"available\":" + (available ? "true" : "false") + ","
            + "\"fuel_state\":\"" + fuel + "\","
            + "\"id\":\"" + id + "\","
            + "\"installed\":" + (installed ? "true" : "false") + ","
            + "\"label\":\"" + label + "\","
            + "\"reason\":\"" + Esc(reason) + "\"}";
    }

    private static string Esc(string value)
    {
        return (value ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"");
    }

    private static bool Is(string arg, string name)
    {
        return string.Equals(arg, name, StringComparison.OrdinalIgnoreCase);
    }

    private static bool Take(string[] args, ref int i, out string value)
    {
        if (i + 1 >= args.Length || (args[i + 1] ?? "").StartsWith('-'))
        {
            value = "";
            return false;
        }

        i++;
        value = args[i] ?? "";
        return true;
    }
}

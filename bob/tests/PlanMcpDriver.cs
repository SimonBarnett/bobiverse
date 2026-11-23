using System;
using System.IO;

internal static class PlanMcpDriver
{
    static int Main()
    {
        if (BobDialogs.PlanMcpConfig.Url != "https://plan.ntsa.uk/mcp") return 1;
        if (BobDialogs.PlanMcpConfig.Json().IndexOf("https://plan.ntsa.uk/mcp") < 0) return 2;
        string dir = Path.Combine(Path.GetTempPath(), "bob-plan-mcp-" + System.Guid.NewGuid().ToString("n"));
        Directory.CreateDirectory(dir);
        string path = BobDialogs.PlanMcpConfig.WriteConfig(dir);
        string raw = File.ReadAllText(path);
        if (raw.IndexOf("https://plan.ntsa.uk/mcp") < 0) return 3;
        Console.WriteLine("plan-mcp url=" + BobDialogs.PlanMcpConfig.Url);
        return 0;
    }
}

using System.IO;

namespace BobDialogs
{
    public static class PlanMcpConfig
    {
        public const string Url = "https://plan.ntsa.uk/mcp";

        public static string Json()
        {
            return "{\"mcpServers\":{\"plan\":{\"url\":\"" + Url + "\"}}}";
        }

        public static string WriteConfig(string root)
        {
            string dir = Path.Combine(root ?? "", "run");
            Directory.CreateDirectory(dir);
            string path = Path.Combine(dir, "plan-mcp.json");
            File.WriteAllText(path, Json());
            return path;
        }
    }
}

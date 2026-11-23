namespace BobDialogs
{
    /// <summary>FR #8682 / BOB-38: Agents &gt; Jeeves loads skills from the J: skill-dag MCP root.</summary>
    public static class JeevesJMcp
    {
        public const string SkillsRoot = @"J:\.grok\skills";
        public const string EnvName = "BOB_JEEVES_MCP_ROOT";

        public static string DryRunLine()
        {
            return "jeeves-mcp path=" + SkillsRoot;
        }
    }
}

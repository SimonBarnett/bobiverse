namespace BobDialogs
{
    /// <summary>FR #8683 / BOB-39: Agents &gt; Jeeves uses a lazy skill DAG on J: skills.</summary>
    public static class JeevesLazyDag
    {
        public const string DefaultSkillsRoot = @"J:\.grok\skills";

        public static string DryRunLine()
        {
            return "jeeves-dag lazy root=" + DefaultSkillsRoot;
        }
    }
}

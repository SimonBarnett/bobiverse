using System.Text.RegularExpressions;

namespace BobDialogs
{
    public static class PlanModelsWebhook
    {
        public static string DryRunLine(string json)
        {
            if (string.IsNullOrEmpty(json)) return "";
            Match block = Regex.Match(json, "\"Plan\"\\s*:\\s*\\{([^}]+)\\}");
            if (!block.Success) return "";
            string body = block.Groups[1].Value;
            string model = Field(body, "model");
            string context = Field(body, "context");
            string effort = Field(body, "effort");
            if (model.Length == 0 && context.Length == 0 && effort.Length == 0) return "";
            return "plan-models webhook model=" + model + " context=" + context + " effort=" + effort;
        }

        static string Field(string body, string name)
        {
            Match m = Regex.Match(body, "\"" + name + "\"\\s*:\\s*\"([^\"]*)\"");
            return m.Success ? m.Groups[1].Value : "";
        }
    }
}

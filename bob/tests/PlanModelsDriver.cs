using System;

internal static class PlanModelsDriver
{
    static int Main()
    {
        string json = "{\"Plan\":{\"model\":\"grok-4\",\"context\":\"200000\",\"effort\":\"low\"}}";
        string line = BobDialogs.PlanModelsWebhook.DryRunLine(json);
        if (line != "plan-models webhook model=grok-4 context=200000 effort=low") return 1;
        if (BobDialogs.PlanModelsWebhook.DryRunLine("{\"Jeeves\":{\"model\":\"x\"}}").Length != 0) return 2;
        Console.WriteLine(line);
        return 0;
    }
}

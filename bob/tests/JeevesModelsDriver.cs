using System;

internal static class JeevesModelsDriver
{
    static int Main()
    {
        string json = "{\"Jeeves\":{\"model\":\"grok-4\",\"context\":\"200000\",\"effort\":\"low\"}}";
        string line = BobDialogs.JeevesModelsWebhook.DryRunLine(json);
        if (line != "jeeves-models webhook model=grok-4 context=200000 effort=low") return 1;
        if (BobDialogs.JeevesModelsWebhook.DryRunLine("{\"Grok\":{\"model\":\"x\"}}").Length != 0) return 2;
        Console.WriteLine(line);
        return 0;
    }
}

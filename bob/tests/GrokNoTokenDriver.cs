using System;

internal static class GrokNoTokenDriver
{
    static int Main()
    {
        if (!BobDialogs.GrokNoTokenGate.IsEmptyDocument("{\"remaining_pct\":0}")) return 1;
        if (BobDialogs.GrokNoTokenGate.IsEmptyDocument("{\"remaining_pct\":40}")) return 2;
        if (BobDialogs.GrokNoTokenGate.IsEmptyDocument("")) return 3;
        if (BobDialogs.GrokNoTokenGate.ShouldQuit("", "")) return 4;
        Console.WriteLine("dialog-quit no-start");
        return 0;
    }
}

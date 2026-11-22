using System;

internal static class JeevesNoTokenDriver
{
    static int Main()
    {
        if (!BobDialogs.JeevesNoTokenGate.IsEmptyDocument("{\"remaining_pct\":0}")) return 1;
        if (BobDialogs.JeevesNoTokenGate.IsEmptyDocument("{\"remaining_pct\":40}")) return 2;
        if (BobDialogs.JeevesNoTokenGate.IsEmptyDocument("")) return 3;
        Console.WriteLine("dialog-quit no-start");
        return 0;
    }
}

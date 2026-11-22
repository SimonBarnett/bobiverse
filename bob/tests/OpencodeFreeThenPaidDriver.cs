using System;

internal static class OpencodeFreeThenPaidDriver
{
    static int Main()
    {
        string paid = BobDialogs.OpencodeFreeThenPaid.Choose("{\"free\":0,\"paid\":5}");
        string free = BobDialogs.OpencodeFreeThenPaid.Choose("{\"free\":3,\"paid\":5}");
        string none = BobDialogs.OpencodeFreeThenPaid.Choose("");
        if (paid != "paid") return 1;
        if (free != "free") return 2;
        if (none != "") return 3;
        Console.WriteLine("slot=paid");
        return 0;
    }
}

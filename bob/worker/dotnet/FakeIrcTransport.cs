// FR #9804: in-memory IRC transport for contract / --self-test-irc (no live Ergo).
using System.Collections.Concurrent;

namespace Bobiverse.WorkerNet;

internal sealed class FakeIrcTransport : IIrcTransport
{
    private readonly ConcurrentQueue<string> _inbox = new();
    private readonly List<string> _sent = new();
    private readonly object _gate = new();
    private bool _connected;

    public IReadOnlyList<string> Sent
    {
        get { lock (_gate) { return _sent.ToList(); } }
    }

    public void EnqueueServerLine(string line) => _inbox.Enqueue(line);

    /// <summary>Auto-reply 001 + JOIN echo after NICK/USER (and optional PASS).</summary>
    public void ArmWelcome(string nick, string shopChannel)
    {
        // Reader loop will pull these after client writes NICK/USER.
        EnqueueServerLine($":ergo.example 001 {nick} :Welcome");
        EnqueueServerLine($":{nick}!seat@worker JOIN {shopChannel}");
    }

    public void Connect(string host, int port, bool useTls, TimeSpan connectTimeout)
    {
        _ = host;
        _ = port;
        _ = useTls;
        _ = connectTimeout;
        _connected = true;
    }

    public void WriteLine(string line)
    {
        if (!_connected)
        {
            throw new InvalidOperationException("fake IRC not connected");
        }

        lock (_gate)
        {
            _sent.Add(line);
        }
    }

    public bool TryReadLine(out string line, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow <= deadline)
        {
            if (_inbox.TryDequeue(out var got) && got != null)
            {
                line = got;
                return true;
            }

            Thread.Sleep(5);
        }

        line = "";
        return false;
    }

    public void Dispose() => _connected = false;
}

// FR #9804: TLS IRC seat — PASS/NICK/USER, wait 001, JOIN #machine, fail closed without JOIN.
namespace Bobiverse.WorkerNet;

/// <summary>
/// Shop IRC seat. Agent spawn must not open until <see cref="CanStartAgent"/> is true
/// (registered + JOINed). Parity with Python <c>IrcSeat.connect_with_retries</c> (FR #955 / #1002).
/// </summary>
internal sealed class IrcSeat : IDisposable
{
    public const string DefaultHost = "irc.ntsa.uk";
    public const int DefaultPort = 6697;

    private readonly IIrcTransport _transport;
    private readonly Action<string> _log;
    private bool _disposed;

    public string Host { get; }
    public int Port { get; }
    public string Nick { get; }
    public string Machine { get; }
    public string ShopChannel => "#" + Machine.TrimStart('#').ToLowerInvariant();
    public bool UseTls { get; }
    /// <summary>PASS secret — never logged.</summary>
    public string? Password { get; }

    public bool IsRegistered { get; private set; }
    public bool IsJoined { get; private set; }
    public string? Failed { get; private set; }

    /// <summary>FR #9804 / #1002: start_agent gate — false until JOIN confirmed.</summary>
    public bool CanStartAgent =>
        !_disposed && Failed is null && IsRegistered && IsJoined;

    public IrcSeat(
        string nick,
        string machine,
        string? password = null,
        string host = DefaultHost,
        int port = DefaultPort,
        bool useTls = true,
        IIrcTransport? transport = null,
        Action<string>? log = null)
    {
        Nick = string.IsNullOrWhiteSpace(nick)
            ? throw new ArgumentException("nick required", nameof(nick))
            : nick.Trim();
        Machine = string.IsNullOrWhiteSpace(machine)
            ? throw new ArgumentException("machine required", nameof(machine))
            : machine.Trim().TrimStart('#').ToLowerInvariant();
        Password = string.IsNullOrWhiteSpace(password) ? null : password;
        Host = string.IsNullOrWhiteSpace(host) ? DefaultHost : host.Trim();
        Port = port > 0 ? port : DefaultPort;
        UseTls = useTls;
        _transport = transport ?? new SslStreamIrcTransport();
        _log = log ?? (_ => { });
    }

    public void Connect(TimeSpan? timeout = null)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ResetAttemptState();
        var budget = timeout ?? TimeSpan.FromSeconds(45);
        var deadline = DateTime.UtcNow + budget;

        _transport.Connect(Host, Port, UseTls, TimeSpan.FromSeconds(20));

        // Never log Password.
        if (!string.IsNullOrEmpty(Password))
        {
            _transport.WriteLine("PASS " + Password);
        }

        _transport.WriteLine("NICK " + Nick);
        _transport.WriteLine($"USER {Nick} 0 * :bobiverse worker seat");

        PumpUntil(() => IsRegistered || Failed != null, deadline, "IRC registration timed out");
        if (Failed != null)
        {
            throw new IOException(Failed);
        }

        _transport.WriteLine("JOIN " + ShopChannel);
        PumpUntil(() => IsJoined || Failed != null, deadline, "IRC JOIN timed out");
        if (Failed != null)
        {
            throw new IOException(Failed);
        }

        if (!CanStartAgent)
        {
            throw new IOException("IRC JOIN incomplete — start_agent gate closed");
        }
    }

    /// <summary>FR #955 parity: retry registration/JOIN with backoff before fail-closed.</summary>
    public void ConnectWithRetries(
        int attempts = 3,
        TimeSpan? timeout = null,
        double[]? backoffSeconds = null)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        var n = Math.Max(1, attempts);
        var backs = backoffSeconds is { Length: > 0 } ? backoffSeconds : new[] { 2.0, 5.0, 10.0 };
        Exception? last = null;
        for (var i = 0; i < n; i++)
        {
            try
            {
                Connect(timeout);
                if (i > 0)
                {
                    _log($"IRC: connected on attempt {i + 1}/{n}");
                }

                return;
            }
            catch (Exception ex)
            {
                last = ex;
                _log($"IRC: connect attempt {i + 1}/{n} failed ({ex.GetType().Name}: {Trim(ex.Message, 120)})");
                try { _transport.Dispose(); } catch { /* ignore */ }
                if (i + 1 >= n)
                {
                    break;
                }

                var delay = backs[Math.Min(i, backs.Length - 1)];
                Thread.Sleep(TimeSpan.FromSeconds(delay));
            }
        }

        throw last ?? new IOException("IRC connect_with_retries exhausted");
    }

    private void PumpUntil(Func<bool> done, DateTime deadlineUtc, string timeoutMessage)
    {
        while (!done())
        {
            var left = deadlineUtc - DateTime.UtcNow;
            if (left <= TimeSpan.Zero)
            {
                Failed = timeoutMessage;
                throw new TimeoutException(timeoutMessage);
            }

            if (!_transport.TryReadLine(out var line, left))
            {
                continue;
            }

            HandleLine(line);
            if (Failed != null)
            {
                return;
            }
        }
    }

    internal void HandleLine(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return;
        }

        // PING
        if (raw.StartsWith("PING ", StringComparison.OrdinalIgnoreCase))
        {
            var payload = raw.Length > 5 ? raw[5..] : "";
            _transport.WriteLine("PONG " + payload);
            return;
        }

        var (prefix, command, args) = Parse(raw);
        if (string.Equals(command, "001", StringComparison.Ordinal))
        {
            IsRegistered = true;
            return;
        }

        if (string.Equals(command, "JOIN", StringComparison.OrdinalIgnoreCase))
        {
            var who = NickFromPrefix(prefix);
            var chan = args.FirstOrDefault() ?? "";
            if (string.Equals(who, Nick, StringComparison.OrdinalIgnoreCase)
                && string.Equals(chan, ShopChannel, StringComparison.OrdinalIgnoreCase))
            {
                IsJoined = true;
            }

            return;
        }

        if (string.Equals(command, "ERROR", StringComparison.OrdinalIgnoreCase)
            || string.Equals(command, "465", StringComparison.Ordinal) // banned
            || string.Equals(command, "464", StringComparison.Ordinal)) // bad password
        {
            Failed = "IRC " + command + (args.Count > 0 ? (" " + args[^1]) : "");
        }
    }

    private static (string prefix, string command, List<string> args) Parse(string raw)
    {
        var s = raw;
        var prefix = "";
        if (s.StartsWith(':'))
        {
            var sp = s.IndexOf(' ');
            if (sp < 0)
            {
                return (s[1..], "", new List<string>());
            }

            prefix = s[1..sp];
            s = s[(sp + 1)..];
        }

        var parts = new List<string>();
        while (!string.IsNullOrEmpty(s))
        {
            if (s.StartsWith(':'))
            {
                parts.Add(s[1..]);
                break;
            }

            var sp = s.IndexOf(' ');
            if (sp < 0)
            {
                parts.Add(s);
                break;
            }

            parts.Add(s[..sp]);
            s = s[(sp + 1)..];
        }

        var command = parts.Count > 0 ? parts[0] : "";
        var args = parts.Count > 1 ? parts.Skip(1).ToList() : new List<string>();
        return (prefix, command, args);
    }

    private static string NickFromPrefix(string prefix)
    {
        if (string.IsNullOrEmpty(prefix))
        {
            return "";
        }

        var bang = prefix.IndexOf('!');
        return bang >= 0 ? prefix[..bang] : prefix;
    }

    private void ResetAttemptState()
    {
        IsRegistered = false;
        IsJoined = false;
        Failed = null;
    }

    private static string Trim(string s, int max) =>
        string.IsNullOrEmpty(s) ? "" : (s.Length <= max ? s : s[..max]);

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        try { _transport.Dispose(); } catch { /* ignore */ }
    }
}

/// <summary>FR #9804: spawn gate — agent must not start without JOIN.</summary>
internal static class StartAgentGate
{
    public static bool IsOpen(IrcSeat? seat) => seat is not null && seat.CanStartAgent;

    public static void EnsureOpen(IrcSeat? seat)
    {
        if (!IsOpen(seat))
        {
            throw new InvalidOperationException(
                "start_agent gate closed: IRC JOIN required before spawn (FR #9804)");
        }
    }
}

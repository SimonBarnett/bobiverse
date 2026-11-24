// FR #9804: production IRC transport — TcpClient + SslStream (TLS).
using System.Net.Security;
using System.Net.Sockets;
using System.Text;

namespace Bobiverse.WorkerNet;

internal sealed class SslStreamIrcTransport : IIrcTransport
{
    private TcpClient? _tcp;
    private Stream? _stream;
    private readonly StringBuilder _buf = new();
    private readonly byte[] _readBuf = new byte[4096];

    public void Connect(string host, int port, bool useTls, TimeSpan connectTimeout)
    {
        Dispose();
        var tcp = new TcpClient();
        var connectTask = tcp.ConnectAsync(host, port);
        if (!connectTask.Wait(connectTimeout))
        {
            try { tcp.Dispose(); } catch { /* ignore */ }
            throw new TimeoutException($"IRC TCP connect timed out ({host}:{port})");
        }

        connectTask.GetAwaiter().GetResult();
        Stream stream = tcp.GetStream();
        if (useTls)
        {
            var ssl = new SslStream(stream, leaveInnerStreamOpen: false);
            ssl.AuthenticateAsClient(host);
            stream = ssl;
        }

        _tcp = tcp;
        _stream = stream;
    }

    public void WriteLine(string line)
    {
        if (_stream is null)
        {
            throw new InvalidOperationException("IRC transport not connected");
        }

        var sanitized = (line ?? "").Replace("\r", " ").Replace("\n", " ");
        var data = Encoding.UTF8.GetBytes(sanitized + "\r\n");
        _stream.Write(data, 0, data.Length);
        _stream.Flush();
    }

    public bool TryReadLine(out string line, TimeSpan timeout)
    {
        line = "";
        if (_stream is null)
        {
            return false;
        }

        var deadline = DateTime.UtcNow + timeout;
        while (true)
        {
            var existing = ExtractLine();
            if (existing != null)
            {
                line = existing;
                return true;
            }

            var left = deadline - DateTime.UtcNow;
            if (left <= TimeSpan.Zero)
            {
                return false;
            }

            if (_tcp?.Client != null)
            {
                _tcp.Client.ReceiveTimeout = (int)Math.Clamp(left.TotalMilliseconds, 1, int.MaxValue);
            }

            int n;
            try
            {
                n = _stream.Read(_readBuf, 0, _readBuf.Length);
            }
            catch (IOException)
            {
                return false;
            }

            if (n <= 0)
            {
                return false;
            }

            _buf.Append(Encoding.UTF8.GetString(_readBuf, 0, n));
        }
    }

    private string? ExtractLine()
    {
        var s = _buf.ToString();
        var idx = s.IndexOf('\n');
        if (idx < 0)
        {
            return null;
        }

        var raw = s[..idx].TrimEnd('\r');
        _buf.Clear();
        if (idx + 1 < s.Length)
        {
            _buf.Append(s[(idx + 1)..]);
        }

        return raw;
    }

    public void Dispose()
    {
        try { _stream?.Dispose(); } catch { /* ignore */ }
        try { _tcp?.Dispose(); } catch { /* ignore */ }
        _stream = null;
        _tcp = null;
        _buf.Clear();
    }
}

// FR #9804: injectable IRC byte transport (SslStream production; fake for tests).
namespace Bobiverse.WorkerNet;

internal interface IIrcTransport : IDisposable
{
    void Connect(string host, int port, bool useTls, TimeSpan connectTimeout);
    void WriteLine(string line);
    /// <summary>Read one IRC line (without CR/LF). Returns false on timeout / EOF.</summary>
    bool TryReadLine(out string line, TimeSpan timeout);
}

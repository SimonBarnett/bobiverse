// FR #9806 uses Stop() before spawn; full spinner UX is FR-C #9802.
namespace Bobiverse.WorkerNet;

/// <summary>
/// Named pre-TUI progress. FR #9806 only needs Stop() so the spinner line is
/// cleared before the agent inherits the console (FR-C #9802 owns the spinner).
/// </summary>
internal sealed class StartupProgress : IDisposable
{
    private readonly TextWriter _out;
    private readonly bool _enabled;
    private bool _active;
    private bool _stopped;

    internal StartupProgress(TextWriter? writer = null)
    {
        _out = writer ?? Console.Out;
        var opt = Environment.GetEnvironmentVariable("BOB_WORKER_STARTUP_PROGRESS");
        _enabled = !string.Equals(opt, "0", StringComparison.Ordinal);
    }

    internal bool IsActive => _active && !_stopped;

    internal void Start(string step)
    {
        if (!_enabled || _stopped)
        {
            return;
        }

        _active = true;
        _out.Write("\rstartup-step " + step + " ...");
        _out.Flush();
    }

    /// <summary>Clear the spinner line before spawn so the agent TUI owns the console.</summary>
    internal void Stop()
    {
        if (_stopped)
        {
            return;
        }

        _stopped = true;
        if (_active && _enabled)
        {
            _out.Write("\r" + new string(' ', 72) + "\r");
            _out.Flush();
        }

        _active = false;
    }

    public void Dispose() => Stop();
}

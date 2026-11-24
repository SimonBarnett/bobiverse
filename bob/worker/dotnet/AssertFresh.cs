// FR #9806: always-new agent argv (parity with Python bob_worker.assert_fresh / t765u).
using System.Text.RegularExpressions;

namespace Bobiverse.WorkerNet;

internal static class AssertFresh
{
    /// <summary>Flags that would reuse or attach to an existing agent session.</summary>
    internal static readonly string[] ForbiddenFlags =
    {
        "--resume", "-r", "--continue", "-c", "--resume-session", "--session", "--chat",
    };

    /// <summary>
    /// Refuse argv (and optional launcher script bodies) that resume/continue/attach.
    /// Maintenance allow_resume is out of scope for Phase 3 FR-G.
    /// </summary>
    internal static void Assert(IReadOnlyList<string> argv, IReadOnlyDictionary<string, string>? files = null)
    {
        foreach (var a in argv)
        {
            if (ForbiddenFlags.Contains(a, StringComparer.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    "refusing to launch: '" + a + "' would reuse an existing agent session");
            }
        }

        if (files is null)
        {
            return;
        }

        var rx = new Regex(@"(?i)(^|\s)(--resume|--continue|-r|-c)(\s|=|$)", RegexOptions.CultureInvariant);
        foreach (var text in files.Values)
        {
            if (rx.IsMatch(text ?? ""))
            {
                throw new InvalidOperationException(
                    "refusing to launch: launcher script would resume/continue an agent session");
            }
        }
    }
}

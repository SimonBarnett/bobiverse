// FR #9804: Ergo PASS search paths parity with Python bob_worker.find_ergo_password.
// Never log or return paths that would print the secret value.
namespace Bobiverse.WorkerNet;

internal static class ErgoPassword
{
    /// <summary>
    /// Resolve IRC PASS from env then the same on-disk search paths as Python
    /// <c>find_ergo_password</c>. Returns null when none found. Caller must not log the value.
    /// </summary>
    public static string? Find(string installRoot, IDictionary<string, string>? env = null)
    {
        string? GetEnv(string key)
        {
            if (env != null && env.TryGetValue(key, out var v) && !string.IsNullOrWhiteSpace(v))
            {
                return v.Trim();
            }

            return Environment.GetEnvironmentVariable(key)?.Trim();
        }

        var fromEnv = GetEnv("BOB_IRC_PASSWORD");
        if (!string.IsNullOrEmpty(fromEnv))
        {
            return fromEnv;
        }

        var root = string.IsNullOrWhiteSpace(installRoot)
            ? Directory.GetCurrentDirectory()
            : installRoot;
        var up = GetEnv("USERPROFILE");
        if (string.IsNullOrWhiteSpace(up))
        {
            up = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        }

        foreach (var candidate in CandidatePaths(root, up ?? ""))
        {
            try
            {
                if (!File.Exists(candidate))
                {
                    continue;
                }

                var text = File.ReadAllText(candidate).Trim().TrimStart('\uFEFF');
                if (!string.IsNullOrEmpty(text))
                {
                    return text;
                }
            }
            catch (IOException)
            {
                // skip unreadable
            }
            catch (UnauthorizedAccessException)
            {
                // skip
            }
        }

        return null;
    }

    /// <summary>Public for contract tests — paths only, never file contents.</summary>
    internal static IEnumerable<string> CandidatePaths(string installRoot, string userProfile)
    {
        yield return Path.Combine(installRoot, "home", "ergo.password");
        yield return Path.Combine(installRoot, "config", "ergo.password");
        if (!string.IsNullOrWhiteSpace(userProfile))
        {
            yield return Path.Combine(userProfile, ".bobiverse", "ergo.password");
            yield return Path.Combine(userProfile, ".grok", "ergo", "connect.password");
            yield return Path.Combine(userProfile, ".grok", "ergo", "ergo.password");
        }
    }
}

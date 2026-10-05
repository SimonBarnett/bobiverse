// FR #2411: unhandled exception hook for bob-about / bob-status / bob-tray.
// Spools a crash report JSON under %LOCALAPPDATA%\Bobiverse\crash-spool (Python flush on next start).
// Never rethrows from the handler. Referenced by BobDialogsCommon / dialog Main entrypoints.
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace BobDialogs
{
    internal static class CrashHook
    {
        static int installed;
        static string product = "bob-dialogs";

        public static void Install(string productName)
        {
            if (Interlocked.Exchange(ref installed, 1) == 1) return;
            product = string.IsNullOrEmpty(productName) ? "bob-dialogs" : productName;
            try
            {
                Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            }
            catch { }
            Application.ThreadException += OnThreadException;
            AppDomain.CurrentDomain.UnhandledException += OnUnhandled;
        }

        static void OnThreadException(object sender, System.Threading.ThreadExceptionEventArgs e)
        {
            try { WriteSpool(e.Exception); } catch { }
        }

        static void OnUnhandled(object sender, UnhandledExceptionEventArgs e)
        {
            try { WriteSpool(e.ExceptionObject as Exception); } catch { }
        }

        static void WriteSpool(Exception ex)
        {
            string root = Environment.GetEnvironmentVariable("BOB_CRASH_SPOOL");
            if (string.IsNullOrEmpty(root))
            {
                string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                root = Path.Combine(local, "Bobiverse", "crash-spool");
            }
            Directory.CreateDirectory(root);
            string typeName = ex == null ? "Exception" : ex.GetType().Name;
            string msg = ex == null ? "" : (ex.Message ?? "");
            string sig = (typeName + ":" + msg).GetHashCode().ToString("x8");
            string path = Path.Combine(root, "crash-csharp-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss") + "-" + sig + ".json");
            string stack = ex == null ? "" : (ex.ToString() ?? "");
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.Append("  \"sig\": \"").Append(Esc(sig)).AppendLine("\",");
            sb.Append("  \"title\": \"crash: ").Append(Esc(product)).Append(" ").Append(Esc(typeName)).Append(" [").Append(Esc(sig)).AppendLine("]\",");
            sb.AppendLine("  \"repo\": \"SimonBarnett/bobiverse\",");
            sb.Append("  \"body\": \"<!-- crash-sig:").Append(Esc(sig)).Append(" -->\\n");
            sb.Append("crash-sig: `").Append(Esc(sig)).Append("`\\n\\n");
            sb.Append("### Process\\n```\\nexe=").Append(Esc(product)).Append("\\nmachine=");
            sb.Append(Esc(Environment.MachineName)).Append("\\n```\\n\\n");
            sb.Append("### Exception\\n`").Append(Esc(stack)).Append("`\\n\\n");
            sb.AppendLine("_Auto-filed by CrashHook (FR #2411)._\"\n}");
            File.WriteAllText(path, sb.ToString(), Encoding.UTF8);
        }

        static string Esc(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", " ").Replace("\n", "\\n");
        }
    }
}

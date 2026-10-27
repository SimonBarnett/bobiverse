"""FR #5050: fail the build if designated runtime windows regain an empty catch."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
JEEVES = ROOT / "common" / "scripts" / "jeeves_main.py"
EAR = ROOT / "common" / "scripts" / "irc_agent.py"

_EMPTY_PS = re.compile(r"catch\s*\{\s*\}", re.I)
_EMPTY_PY = re.compile(r"except Exception:\s*\n\s*pass\b")


def test_fr5050_digest_timer_window_has_no_empty_catch():
    t = WATCH.read_text(encoding="utf-8-sig")
    start = t.index("Write-BobIrcStatus | Out-Null")
    # The digest Action's Write-BobIrcStatus catch (not the startup one).
    digest = t[t.index("$script:trayDigestSub = Register-ObjectEvent") :]
    inner = digest[digest.index("Write-BobIrcStatus | Out-Null") :]
    catch = inner[inner.index("} catch {") : inner.index("    }\n    catch {")]
    assert "FR #5050" in catch
    assert "Report-BobRuntimeFailure" in catch
    assert not re.search(r"Write-BobIrcStatus \| Out-Null\s*\n\s*\} catch \{ \}", digest)


def test_fr5050_jeeves_crash_install_reports():
    t = JEEVES.read_text(encoding="utf-8")
    start = t.index("def main(")
    window = t[start : start + 800]
    assert "runtime_failure" in window or "report(" in window
    assert "except Exception:\n        pass" not in window


def test_fr5050_ear_installs_and_reports_caught():
    t = EAR.read_text(encoding="utf-8")
    assert "crash_report.install" in t
    assert "runtime_failure" in t

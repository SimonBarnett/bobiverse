"""FR #2436: C# CrashHook must skip do-not-file / probe-shape markers like Python crash_report."""
from __future__ import annotations

from repo_layout import resolve


def _hook_text() -> str:
    return resolve("third_party/bob-tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")


def test_csharp_should_skip_report_mirrors_python_markers():
    text = _hook_text()
    assert "ShouldSkipReport" in text
    assert "DoNotFileRe" in text
    assert "do-not-file" in text
    assert "probe-shape-only" in text
    assert 'name == "probe"' in text
    assert 'name == "crash-probe"' in text
    assert 'name == "crash_probe"' in text
    # Report and FlushSpool must gate before intake/spool.
    assert "if (ShouldSkipReport(exeName, ex))" in text
    assert "ShouldSkipReport(exe, null, body, title)" in text
    assert "FR #2436" in text


def test_csharp_skip_parity_with_python_should_skip_report():
    """Source gate: C# markers stay aligned with crash_report.should_skip_report."""
    import crash_report

    py = resolve("common/scripts/crash_report.py").read_text(encoding="utf-8")
    assert "should_skip_report" in py
    assert "do-not-file|probe-shape-only" in py
    assert '"probe"' in py and '"crash-probe"' in py

    cs = _hook_text()
    for marker in ("do-not-file", "probe-shape-only", "crash-probe", "crash_probe"):
        assert marker in cs

    # Runtime sanity on the Python side the C# gate mirrors.
    assert crash_report.should_skip_report("probe", RuntimeError("x"))
    assert crash_report.should_skip_report("bob-tray", RuntimeError("probe-shape-only-do-not-file"))
    assert not crash_report.should_skip_report("bob-tray", RuntimeError("real boom"))

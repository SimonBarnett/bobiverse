"""FR #3328: C# CrashHook must honour BOB_CRASH_REPORT / crash-report.json (parity with FR #3291)."""
from __future__ import annotations

from repo_layout import resolve


def _hook_text() -> str:
    return resolve("third_party/bob-tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")


def test_fr3328_csharp_has_crash_report_policy_types():
    text = _hook_text()
    assert "FR #3328" in text
    assert "class CrashReportPolicy" in text
    assert "LoadCrashReportPolicy" in text
    assert "BOB_CRASH_REPORT" in text
    assert "crash-report.json" in text
    assert "BOB_CRASH_REPORT_CONFIG" in text
    assert "local-only" in text
    assert "local_only" in text
    assert 'envRaw == "0"' in text or 'envRaw == "off"' in text
    assert "airc-shell-off" in text


def test_fr3328_csharp_report_and_flush_gate_on_policy_send():
    """Report spools locally when !Send; FlushSpool keeps files; TryPostIntake refuses."""
    text = _hook_text()
    assert "if (!policy.Send)" in text
    assert 'WriteSpool(title, body, sig, exeName, "local_only")' in text
    # FlushSpool early-return while disabled
    assert "if (!policy.Send) return;" in text
    # TryPostIntake defense in depth
    assert "if (!policy.Send) return false;" in text
    # Install only flushes when send allowed
    assert "if (policy.Send) FlushSpool()" in text


def test_fr3328_csharp_precedence_mirrors_python_fr3291():
    """Source gate: env > config > airc shell=off > fleet on (same as load_crash_report_policy)."""
    text = _hook_text()
    assert "ResolveCrashReportPolicy" in text or "LoadCrashReportPolicy" in text
    # Config modes
    assert 'modeRaw == "local-only"' in text or 'modeRaw == "local_only"' in text
    assert 'cfg.ContainsKey("enabled")' in text
    # Env overrides after config
    assert 'Environment.GetEnvironmentVariable("BOB_CRASH_REPORT")' in text
    # Airc shell=off default
    assert "AircShellOff" in text
    assert 'shell == "off"' in text

    py = resolve("common/scripts/crash_report.py").read_text(encoding="utf-8")
    assert "load_crash_report_policy" in py
    assert "BOB_CRASH_REPORT" in py
    assert "CrashReportPolicy" in py
    assert "airc-shell-off" in py or "airc shell=off" in py.lower()


def test_fr3328_python_opt_out_still_green():
    """Runtime sanity: Python side the C# gate mirrors still works (FR #3291)."""
    import os
    from unittest import mock

    import crash_report

    os.environ["BOB_CRASH_REPORT"] = "0"
    try:
        crash_report._policy_cache = None
        p = crash_report.load_crash_report_policy()
        assert p.send is False
        with mock.patch("crash_report.urllib.request.urlopen") as urlopen:
            try:
                raise RuntimeError("fr3328-parity")
            except RuntimeError as exc:
                result = crash_report.report_exception(
                    "bob-tray", type(exc), exc, exc.__traceback__
                )
        assert result.get("local_only") is True
        urlopen.assert_not_called()
    finally:
        os.environ.pop("BOB_CRASH_REPORT", None)
        crash_report._policy_cache = None

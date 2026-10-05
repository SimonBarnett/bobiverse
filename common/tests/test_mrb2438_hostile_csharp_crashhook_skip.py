"""MRB #2438 hostile: CrashHook skip gates stay tight vs Python crash_report."""
from __future__ import annotations

import re

import crash_report
from repo_layout import ROOT, resolve

HOOK = resolve("third_party/bob-tray/dialogs/CrashHook.cs")
BUILD = ROOT / "bob/scripts/Build-BobDialogs.ps1"
PY = ROOT / "common/scripts/crash_report.py"


def _cs() -> str:
    return HOOK.read_text(encoding="utf-8-sig")


def test_mrb2438_report_skips_before_signature_and_intake():
    text = _cs()
    # Early return must precede Signature / TryPostIntake / WriteSpool in Report.
    report = text.split("public static void Report(", 1)[1].split("public static void FlushSpool", 1)[0]
    skip_at = report.index("ShouldSkipReport(exeName, ex)")
    sig_at = report.index("Signature(ex)")
    post_at = report.index("TryPostIntake")
    assert skip_at < sig_at < post_at
    assert "return;" in report[skip_at : sig_at + 20]


def test_mrb2438_flush_drops_probe_spool_before_post():
    text = _cs()
    flush = text.split("public static void FlushSpool", 1)[1]
    skip_at = flush.index("ShouldSkipReport(exe, null, body, title)")
    post_at = flush.index("TryPostIntake(title, body, sig, exe)")
    assert skip_at < post_at
    assert "File.Delete(path)" in flush[skip_at:post_at]


def test_mrb2438_probe_exe_set_matches_python():
    py = PY.read_text(encoding="utf-8")
    m = re.search(r"_PROBE_EXE\s*=\s*frozenset\(\{([^}]+)\}\)", py)
    assert m
    py_names = {x.strip().strip("\"'") for x in m.group(1).split(",")}
    cs = _cs()
    for name in py_names:
        assert f'name == "{name}"' in cs, name
    assert "ToLowerInvariant" in cs


def test_mrb2438_donotfile_regex_parity():
    py = PY.read_text(encoding="utf-8")
    assert 'r"(?i)do-not-file|probe-shape-only"' in py or "do-not-file|probe-shape-only" in py
    cs = _cs()
    assert '@"(?i)do-not-file|probe-shape-only"' in cs or "do-not-file|probe-shape-only" in cs
    assert crash_report.should_skip_report("bob-tray", RuntimeError("do-not-file"))
    assert crash_report.should_skip_report("PROBE", RuntimeError("x"))
    assert not crash_report.should_skip_report("bob-about", RuntimeError("disk full"))


def test_mrb2438_build_still_compiles_crashhook():
    build = BUILD.read_text(encoding="utf-8-sig")
    assert "CrashHook.cs" in build
    raw = HOOK.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")

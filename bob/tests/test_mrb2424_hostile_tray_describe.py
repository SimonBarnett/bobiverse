"""Hostile MRB #2424: TipForm must prefer --describe-launch JSON keys and keep fallback/FR1643."""
from __future__ import annotations

from repo_layout import ROOT


def _cs() -> str:
    return (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")


def test_try_describe_reads_canonical_json_keys():
    cs = _cs()
    assert 'Common.Str(d, "run_exe")' in cs
    assert 'Common.Str(d, "cwd")' in cs
    assert 'Common.Str(d, "title")' in cs
    assert 'Common.List(d.ContainsKey("argv")' in cs or 'd["argv"]' in cs
    assert "Common.ParseJson" in cs


def test_launch_prefers_plan_then_fallback_then_createprocess():
    cs = _cs()
    i_plan = cs.index("TryDescribeLaunch(exe")
    i_fallback = cs.index("// Fallback: local hash/argv")
    i_copy = cs.index("File.Copy(exe, run")
    i_create = cs.index("CreateProcessW(run, cmd")
    assert i_plan < i_fallback < i_copy < i_create


def test_fr1643_defer_delete_runs_for_plan_and_fallback_bin():
    cs = _cs()
    assert "string binDir = Path.GetDirectoryName(run)" in cs
    assert 'Directory.GetFiles(binDir, "bob-worker-*.exe")' in cs
    assert "IsWorkerExeInUse(old)" in cs
    assert "FR #1643" in cs


def test_createprocess_uses_plan_title_and_wd():
    cs = _cs()
    assert "si.lpTitle = title" in cs
    assert 'mode == "plan" ? "plan" : "worker"' in cs
    assert "CreateProcessW(run, cmd" in cs


def test_docs_mention_tipform_consumes_describe():
    doc = (ROOT / "bob" / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "FR #2421" in doc
    assert "TipForm" in doc and "describe-launch" in doc
    assert "still embeds matching argv/cwd/hash contract" not in doc

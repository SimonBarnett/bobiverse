"""Hostile MRB #2432: TipForm TryDescribeLaunch must drain stderr on a background thread."""
from __future__ import annotations

from repo_layout import ROOT


def _block() -> str:
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    start = cs.index("static bool TryDescribeLaunch")
    end = cs.index("// Same contract as Start-BobTrayWorkerExe", start)
    return cs[start:end]


def test_stderr_drain_uses_background_thread_before_stdout():
    block = _block()
    assert "RedirectStandardError = true" in block
    assert "System.Threading.Thread" in block
    assert "errThread.IsBackground = true" in block
    assert "errThread.Start()" in block
    i_start = block.index("errThread.Start()")
    i_out = block.index("StandardOutput.ReadToEnd")
    i_join = block.index("errThread.Join")
    assert i_start < i_out < i_join


def test_fr2430_comment_and_readtoend_on_stderr():
    block = _block()
    assert "FR #2430" in block
    assert "StandardError.ReadToEnd" in block
    assert "pipe" in block.lower() or "deadlock" in block.lower()


def test_author_unit_gates_still_present():
    text = (ROOT / "bob" / "tests" / "test_fr2430_describe_stderr_drain.py").read_text(encoding="utf-8")
    assert "StandardError.ReadToEnd" in text
    assert "i_err < i_out" in text

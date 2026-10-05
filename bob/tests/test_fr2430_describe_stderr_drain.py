"""FR #2430: TryDescribeLaunch must drain stderr when redirected (avoid pipe deadlock)."""
from __future__ import annotations

from repo_layout import ROOT


def _try_describe_block() -> str:
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    start = cs.index("static bool TryDescribeLaunch")
    end = cs.index("// Same contract as Start-BobTrayWorkerExe", start)
    return cs[start:end]


def test_try_describe_drains_stderr_when_redirected():
    block = _try_describe_block()
    assert "RedirectStandardError = true" in block
    assert "StandardError.ReadToEnd" in block
    assert "FR #2430" in block


def test_stderr_drain_starts_before_stdout_read():
    block = _try_describe_block()
    i_err = block.index("StandardError.ReadToEnd")
    i_out = block.index("StandardOutput.ReadToEnd")
    assert i_err < i_out

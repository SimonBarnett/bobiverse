# -*- coding: utf-8 -*-
"""FR #9209: OpenCode launch wrapper mirrors capture growth to the seat console live."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw

OP = r"C:\tools\opencode.exe"


def _script(tmp_path: Path) -> str:
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "cwd"),
        "Do work.",
        OP,
        tmp_path / "run",
        None,
    )
    return next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))


def test_fr9209_live_mirror_on_capture_growth(tmp_path: Path):
    ps1 = _script(tmp_path)
    assert "opencode_conpty_run.py" in ps1
    assert "--argv-file" in ps1
    # Live path on growth (not only seat-log when ocStdoutLog set).
    assert "[Console]::Out.Write($slice)" in ps1
    assert "[Console]::Out.Flush()" in ps1
    idx_while = ps1.index("while (-not $proc.HasExited)")
    idx_wait = ps1.index("WaitForExit(2000)", idx_while)
    loop = ps1[idx_while:idx_wait]
    assert "[Console]::Out.Write($slice)" in loop
    assert "ocOutPos" in loop and "ocErrPos" in loop
    # Seat-log tee still optional inside the same growth block.
    assert "stdoutLogPy" in loop or "ocStdoutLog" in loop


def test_fr9209_no_full_outstr_dump_at_end(tmp_path: Path):
    ps1 = _script(tmp_path)
    assert "Write-Output $outStr" not in ps1
    assert "opencode-capture-done" in ps1
    # Fuel scan still builds $outStr from capture files.
    assert "$outStr = $stdout + [Environment]::NewLine + $stderr" in ps1
    assert "$scan = $outStr" in ps1


def test_fr9209_conpty_not_file_redirect(tmp_path: Path):
    """A file redirect makes the CLI buffer until the process exits."""
    ps1 = _script(tmp_path)
    assert "opencode_conpty_run.py" in ps1
    assert "RedirectStandardOutput $outFile" not in ps1
    assert "-NoNewWindow" not in ps1

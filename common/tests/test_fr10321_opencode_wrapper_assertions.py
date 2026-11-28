"""FR #10321: OpenCode launch wrapper contract (ConPTY + env model pin)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw

OP = r"C:\o\opencode.exe"


def test_fr10321_wrapper_uses_conpty_capture_not_exe_redirects(tmp_path: Path):
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "hi", OP, tmp_path)
    script = next(v for k, v in spec.files.items() if k.endswith("launch-opencode.ps1"))
    assert "$conptyPy" in script
    assert "Start-Process -FilePath $pyPty" in script
    assert all(
        "RedirectStandardOutput" not in ln
        for ln in script.splitlines()
        if "Start-Process -FilePath $exe" in ln
    )
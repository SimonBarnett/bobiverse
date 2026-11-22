"""FR #8715 / BOB-12: Weights form grid columns Agent/CLI/Model/Context/Effort."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
WEIGHTS = REPO / "bob" / "tray" / "dialogs" / "WeightsForm.cs"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"
MOCK = REPO / "bob" / "docs" / "mocks" / "systray-agents-workers" / "weights.html"

EXPECTED = ["Agent", "CLI", "Model", "Context", "Effort"]


def test_fr8715_sources_pin_weights_grid_and_dump_flag():
    w = WEIGHTS.read_text(encoding="utf-8-sig")
    t = TRAY.read_text(encoding="utf-8-sig")
    b = BUILD.read_text(encoding="utf-8-sig")
    assert "ColumnHeaders" in w
    for h in EXPECTED:
        assert h in w
    assert "DataGridView" in w
    assert "low" in w and "medium" in w and "high" in w
    assert "256" in w and "512" in w
    # BOB-13 replaces static placeholder rows with webhook data; column contract stays.
    assert "MessageBox.Show" not in t.split("void ShowWeights()")[1].split("void ApplyEngineEnv()")[0]
    assert "new WeightsForm(" in t
    assert "--dump-weights-columns" in t
    assert "WeightsForm.cs" in b
    assert MOCK.is_file()
    mock = MOCK.read_text(encoding="utf-8")
    for h in EXPECTED:
        assert f"<th>{h}</th>" in mock


@pytest.mark.skipif(not (WIN and CSC.is_file() and PS), reason="needs Windows csc and powershell")
def test_fr8715_dump_weights_columns_ordered(tmp_path: Path):
    out_dir = tmp_path / "dlg"
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD),
            "-RepoRoot",
            str(REPO),
            "-OutDir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    tray_exe = out_dir / "bob-tray.exe"
    assert tray_exe.is_file()
    dump = tmp_path / "cols.txt"
    p = subprocess.run(
        [str(tray_exe), "--dump-weights-columns", str(dump), "--no-engine"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    raw = dump.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    lines = [ln.strip() for ln in dump.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines == EXPECTED

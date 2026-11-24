"""FR #9266 / BOB-TRAY-UI-06: Weights Refresh models discovers locally, POSTs catalog, rebinds."""
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
CLIENT = REPO / "bob" / "tray" / "dialogs" / "BobModelsClient.cs"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"
REFRESH_PY = REPO / "common" / "scripts" / "models_refresh.py"


def test_fr9266_sources_pin_refresh_models_flow():
    w = WEIGHTS.read_text(encoding="utf-8-sig")
    c = CLIENT.read_text(encoding="utf-8-sig")
    t = TRAY.read_text(encoding="utf-8-sig")
    py = REFRESH_PY.read_text(encoding="utf-8")

    assert 'Name = "weightsRefresh"' in w or 'refresh.Name = "weightsRefresh"' in w
    assert 'Text = "Refresh models"' in w
    assert "BeginRefreshModels" in w
    assert "DiscoverLocalModels" in w
    assert "PostClientCatalog" in w
    assert "weights_refresh_discover" in w
    assert "weights_refresh_post" in w
    # No validate POST restored (FR #9053).
    assert "/models/validate" not in w
    assert "/models/validate" not in c

    assert "ModelsRefreshPath" in c
    assert 'source' in c and "weights-client" in c
    assert "DiscoverLocalModels" in c
    assert "PostClientCatalog" in c
    assert "ParseGrokModelsText" in c
    assert "ParseOpencodeModelsText" in c
    assert "ResolveGrokExe" in c

    assert "--dump-weights-refresh" in t
    assert "DumpRefreshButton" in w

    assert "weights-client" in py
    assert "CLIENT_SOURCE" in py
    assert "client_catalog" in py


@pytest.mark.skipif(not (WIN and CSC.is_file() and PS), reason="needs Windows csc and powershell")
def test_fr9266_dump_weights_refresh_button(tmp_path: Path):
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
    dump = tmp_path / "refresh.txt"
    p = subprocess.run(
        [str(tray_exe), "--dump-weights-refresh", str(dump), "--no-engine"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    raw = dump.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = dump.read_text(encoding="utf-8")
    assert "weightsRefresh" in text
    assert "Refresh models" in text

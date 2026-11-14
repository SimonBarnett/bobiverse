"""FR #7248: CI tray artifact ships display scripts, not only the dialog exes."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT, REPO

WF = ROOT / ".github" / "workflows" / "build-bob-tray.yml"
STAGE = REPO / "bob" / "scripts" / "Stage-BobTrayHotpatchArtifact.ps1"
INSTALL = REPO / "bob" / "scripts" / "Install-BobTrayHotpatch.ps1"
DOCS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
HOVER = REPO / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell.exe") or "powershell.exe"
MARKER = "FR7248-hover-artifact-marker"


def test_fr7248_workflow_stages_display_scripts():
    text = WF.read_text(encoding="utf-8")
    assert "bob/tray/**" in text
    assert "Stage-BobTrayHotpatchArtifact.ps1" in text
    assert "Get-BobTrayHover.ps1" in text
    assert "Watch-BobTray.ps1" in text or "tools\\Watch-BobTray" in text
    assert "files hashes" in text or 'files.$hoverKey' in text or "hoverKey" in text
    assert "Install-BobTrayHotpatch.ps1" in text
    assert STAGE.is_file()
    assert INSTALL.is_file()
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #7248" in docs
    assert "Install-BobTrayHotpatch" in docs
    assert "Get-BobTrayHover" in docs


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr7248_stage_includes_hover_change_and_hashes(tmp_path: Path):
    """Acceptance: only Get-BobTrayHover.ps1 changes; staged artifact contains it + SHA-256."""
    repo = tmp_path / "repo"
    tray_src = repo / "bob" / "tray" / "src" / "Public"
    tray_tools = repo / "bob" / "tray" / "tools"
    tray_src.mkdir(parents=True)
    tray_tools.mkdir(parents=True)
    (repo / "bob" / "tray" / "assets").mkdir()
    hover = (HOVER.read_text(encoding="utf-8-sig") if HOVER.is_file() else "# hover\n") + f"\n# {MARKER}\n"
    tray_src.joinpath("Get-BobTrayHover.ps1").write_text(hover, encoding="utf-8")
    tray_tools.joinpath("Watch-BobTray.ps1").write_text(
        WATCH.read_text(encoding="utf-8-sig") if WATCH.is_file() else "# watch\n",
        encoding="utf-8",
    )
    stage = tmp_path / "artifact"
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(STAGE),
            "-RepoRoot",
            str(repo),
            "-StageDir",
            str(stage),
            "-Commit",
            "aabbccdd11223344556677889900aabbccddeeff",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    staged_hover = stage / "src" / "Public" / "Get-BobTrayHover.ps1"
    assert staged_hover.is_file()
    assert MARKER in staged_hover.read_text(encoding="utf-8")
    assert (stage / "tools" / "Watch-BobTray.ps1").is_file()
    man = json.loads((stage / "MANIFEST.json").read_text(encoding="utf-8"))
    files = man.get("files") or {}
    key = "src/Public/Get-BobTrayHover.ps1"
    assert key in files, files.keys()
    assert len(files[key]) == 64
    inst = tmp_path / "install"
    inst.mkdir()
    bak = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSTALL),
            "-InstallRoot",
            str(inst),
            "-ArtifactDir",
            str(stage),
            "-BackupDir",
            str(tmp_path / "bak"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert bak.returncode == 0, (bak.stdout or "") + (bak.stderr or "")
    live = inst / "src" / "Public" / "Get-BobTrayHover.ps1"
    assert live.is_file()
    assert MARKER in live.read_text(encoding="utf-8")

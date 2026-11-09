"""FR #6285: CI must compile bob-tray.exe so C# heading changes reach machines.

Reopen gap (9 Nov): digest-only rows merged, but tools\\bob-tray.exe stayed stale
with heading 'Cursor / xAI weekly' because no workflow ran Build-BobDialogs.ps1.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-tray.yml"
BUILD = ROOT / "bob" / "scripts" / "Build-BobDialogs.ps1"
STATUS_CS = ROOT / "bob" / "tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "bob" / "docs" / "bob-tray-dialogs.md"
PS = shutil.which("powershell") or shutil.which("pwsh")


def _wf() -> str:
    return WF.read_text(encoding="utf-8")


def test_fr6285_tray_ci_workflow_pins():
    assert WF.is_file(), "missing .github/workflows/build-bob-tray.yml"
    text = _wf()
    assert "name: build-bob-tray" in text
    assert "runs-on: windows-latest" in text
    assert "Build-BobDialogs.ps1" in text
    assert "bob/tray/**" in text
    assert "persist-credentials: false" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-tray" in text
    assert "provenance.txt" in text
    assert '"$name.sha256"' in text or "exe_sha256_" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "bob-tray.exe" in text
    assert "xAI weekly" in text
    assert "Cursor / xAI weekly" in text  # asserted absent from the PE
    assert "workflow_dispatch" in text
    assert BUILD.is_file()


def test_fr6285_status_cs_heading_and_docs_ci():
    st = STATUS_CS.read_text(encoding="utf-8-sig")
    render = st[st.index("public int Render") : st.index("protected override void OnPaint")]
    assert 'Section(g, y, "xAI weekly"' in render
    assert "Cursor / xAI" not in render

    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #6285" in docs
    assert "build-bob-tray.yml" in docs
    assert "Build-BobDialogs.ps1" in docs


@pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell + csc")
def test_fr6285_local_build_embeds_xai_weekly_heading(tmp_path: Path):
    out = tmp_path / "tray-out"
    out.mkdir()
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD),
            "-RepoRoot",
            str(ROOT),
            "-OutDir",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    tray = out / "bob-tray.exe"
    assert tray.is_file()
    data = tray.read_bytes()
    needle = "xAI weekly".encode("utf-16le")
    bad = "Cursor / xAI weekly".encode("utf-16le")
    assert needle in data, "built bob-tray.exe missing UTF-16LE 'xAI weekly'"
    assert bad not in data, "built bob-tray.exe still has stale Cursor mixed heading"

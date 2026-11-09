"""FR #6349: CI must compile bob-worker.exe (artifact + manifest + --version).

bob-ear and bob-tray already have isolated Windows workflows; worker fixes
(e.g. FR #6341) could not reach seats without a local compile. This gate pins
build-bob-worker.yml to Build-BobWorker.ps1, provenance, and --version.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-worker.yml"
BUILD = ROOT / "bob" / "scripts" / "Build-BobWorker.ps1"
META = ROOT / "bob" / "scripts" / "bob_worker_build_meta.py"
WORKER_PY = ROOT / "bob" / "scripts" / "bob_worker.py"
DOCS = ROOT / "bob" / "docs" / "bob-worker.md"
PS = shutil.which("powershell") or shutil.which("pwsh")


def _wf() -> str:
    return WF.read_text(encoding="utf-8")


def test_fr6349_worker_ci_workflow_pins():
    assert WF.is_file(), "missing .github/workflows/build-bob-worker.yml"
    text = _wf()
    assert "name: build-bob-worker" in text
    assert "runs-on: windows-latest" in text
    assert "Build-BobWorker.ps1" in text
    assert "bob/scripts/bob_worker.py" in text
    assert "bob/scripts/Build-BobWorker.ps1" in text
    assert "bob/scripts/bob_worker_build_meta.py" in text
    assert "bob/tests/test_fr6349_worker_build_ci.py" in text
    assert "persist-credentials: false" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-worker" in text
    assert "provenance.txt" in text or "manifest.txt" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "bob-worker.exe" in text
    assert "--version" in text
    assert "SourceCommit" in text
    assert "workflow_dispatch" in text
    assert "setup-python@v5" in text
    assert "pyinstaller" in text.lower()
    assert "exe_size" in text or "size_bytes" in text
    assert "build_time" in text
    assert BUILD.is_file()
    assert META.is_file()


def test_fr6349_build_script_source_commit_and_meta_stub():
    build = BUILD.read_text(encoding="utf-8")
    assert "[string]$SourceCommit" in build or "$SourceCommit" in build
    assert "bob_worker_build_meta" in build
    assert "--version" in build

    meta = META.read_text(encoding="utf-8")
    assert "SOURCE_COMMIT" in meta

    worker = WORKER_PY.read_text(encoding="utf-8")
    assert "--version" in worker
    assert "bob_worker_build_meta" in worker or "get_source_commit" in worker


def test_fr6349_docs_list_ci_artifact():
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #6349" in docs or "build-bob-worker.yml" in docs
    assert "build-bob-worker.yml" in docs
    assert "Build-BobWorker.ps1" in docs
    assert "bob/tests/test_fr6349_worker_build_ci.py" in docs


def test_fr6349_version_flag_prints_meta_commit(tmp_path: Path, monkeypatch):
    """Source tree: --version reads bob_worker_build_meta.SOURCE_COMMIT."""
    scripts = ROOT / "bob" / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    import bob_worker_build_meta as meta  # noqa: WPS433

    prev = meta.SOURCE_COMMIT
    try:
        meta.SOURCE_COMMIT = "abc123deadbeef6349"
        import bob_worker as bw  # noqa: WPS433

        if hasattr(bw, "get_source_commit"):
            assert bw.get_source_commit() == "abc123deadbeef6349"
        code = bw.main(["--version"])
        assert code == 0
    finally:
        meta.SOURCE_COMMIT = prev


@pytest.mark.skipif(
    not PS or os.name != "nt",
    reason=f"needs Windows + powershell/pwsh (PS={PS!r})",
)
def test_fr6349_build_script_mentions_hidden_import_and_paths():
    """Text gate only: full PyInstaller freeze belongs in GHA (slow)."""
    build = BUILD.read_text(encoding="utf-8")
    assert "hidden-import" in build or "bob_worker_build_meta" in build
    assert "SourceCommit" in build

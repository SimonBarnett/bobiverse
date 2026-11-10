"""FR #6395: CI must compile jeeves.exe (artifact + MANIFEST.json + --version).

Modelled on FR #6349 build-bob-worker. Walrus runs a frozen jeeves.exe; without
a CI artifact, merged chair fixes cannot be installed from a trusted hash.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-jeeves.yml"
BUILD = ROOT / "jeeves" / "scripts" / "Build-Jeeves.ps1"
META = ROOT / "common" / "scripts" / "jeeves_build_meta.py"
MAIN = ROOT / "common" / "scripts" / "jeeves_main.py"
DOCS = ROOT / "jeeves" / "docs" / "jeeves-exe-self-heal.md"


def _wf() -> str:
    return WF.read_text(encoding="utf-8")


def test_fr6395_jeeves_ci_workflow_pins():
    assert WF.is_file(), "missing .github/workflows/build-jeeves.yml"
    text = _wf()
    assert "name: build-jeeves" in text
    assert "runs-on: windows-latest" in text
    assert "Build-Jeeves.ps1" in text
    assert "jeeves/scripts/Build-Jeeves.ps1" in text
    assert "common/scripts/jeeves_main.py" in text or "jeeves/**" in text
    assert "common/**" in text
    assert "common/tests/test_fr6395_jeeves_build_ci.py" in text or "test_fr6395" in text
    assert "persist-credentials: false" in text
    assert "contents: read" in text
    assert "upload-artifact@v4" in text
    assert "name: jeeves" in text
    assert "MANIFEST.json" in text
    assert "jeeves.exe.sha256" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "jeeves.exe" in text
    assert "--version" in text
    assert "SourceCommit" in text
    assert "workflow_dispatch" in text
    assert "setup-python@v5" in text
    assert "python-version: \"3.12\"" in text or "python-version: '3.12'" in text
    assert "pyinstaller" in text.lower()
    assert "workflow_run_id" in text or "github.run_id" in text
    assert "build_time" in text or "built_at" in text or "build_time_utc" in text
    assert BUILD.is_file()
    assert META.is_file()
    assert MAIN.is_file()


def test_fr6395_build_script_source_commit_and_meta_stub():
    build = BUILD.read_text(encoding="utf-8")
    assert "[string]$SourceCommit" in build or "$SourceCommit" in build
    assert "jeeves_build_meta" in build
    assert "--version" in build
    assert "stub-bak" in build or "stubBackup" in build or "stub-bak" in build.replace("_", "-")
    assert "restored" in build.lower() and "jeeves_build_meta" in build
    assert "finally" in build
    assert "ticket_closure" in build and "wake_brief" in build
    assert "stub overwritten for freeze" in build

    meta = META.read_text(encoding="utf-8")
    assert "SOURCE_COMMIT" in meta

    main = MAIN.read_text(encoding="utf-8")
    assert "--version" in main
    assert "jeeves_build_meta" in main or "get_source_commit" in main


def test_fr6395_docs_list_ci_artifact():
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #6395" in docs or "build-jeeves.yml" in docs
    assert "build-jeeves.yml" in docs
    assert "Build-Jeeves.ps1" in docs
    assert "MANIFEST.json" in docs
    assert "sha256" in docs.lower() or "SHA-256" in docs or "SHA256" in docs
    assert "rollback" in docs.lower()


def test_fr6395_version_flag_prints_meta_commit(monkeypatch, capsys):
    scripts = ROOT / "common" / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    import jeeves_build_meta as meta  # noqa: WPS433

    prev = meta.SOURCE_COMMIT
    try:
        meta.SOURCE_COMMIT = "abc123deadbeef6395"
        import jeeves_main as jm  # noqa: WPS433

        importlib.reload(jm)

        if hasattr(jm, "get_source_commit"):
            assert jm.get_source_commit() == "abc123deadbeef6395"
        import crash_report  # noqa: E402

        installs: list = []
        monkeypatch.setattr(crash_report, "install", installs.append)
        capsys.readouterr()
        code = jm.main(["--version"])
        out = capsys.readouterr().out.strip()
        assert code == 0
        assert out == "abc123deadbeef6395"
        assert installs == []
    finally:
        meta.SOURCE_COMMIT = prev


def test_fr6395_manifest_json_shape_in_workflow():
    text = _wf()
    assert "ConvertTo-Json" in text or "MANIFEST.json" in text
    # Must record the fields the FR names.
    low = text.lower()
    assert "source_commit" in low or "sourcecommit" in low
    assert "sha256" in low
    assert "size" in low
    assert "run_id" in low or "runid" in low

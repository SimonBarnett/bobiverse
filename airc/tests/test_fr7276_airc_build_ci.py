"""FR #7276: isolated build-airc.yml (artifact + MANIFEST + path filters)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from airc_ci_source_paths import airc_ci_source_paths, frozen_airc_common_script_paths
from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-airc.yml"
BUILD = ROOT / "airc" / "scripts" / "Build-Airc.ps1"


def _on_block(text: str) -> str:
    m = re.search(r"(?ms)^on:\n(.*?)(?=^permissions:|^jobs:)", text)
    assert m, "workflow missing on: block"
    return m.group(1)


def _event_block(on: str, event: str) -> str:
    m = re.search(
        rf"(?ms)^  {re.escape(event)}:\n(.*?)(?=^  [a-z_]+:|\Z)",
        on,
    )
    assert m, f"on: missing {event} block"
    return m.group(1)


def test_fr7276_workflow_pins():
    assert WF.is_file(), "missing .github/workflows/build-airc.yml"
    text = WF.read_text(encoding="utf-8")
    assert "name: build-airc" in text
    assert "runs-on: windows-latest" in text
    assert "Build-Airc.ps1" in text
    assert "airc/scripts/Build-Airc.ps1" in text
    assert "persist-credentials: false" in text
    assert "contents: read" in text
    assert "upload-artifact@v4" in text
    assert "name: airc" in text
    assert "MANIFEST.json" in text
    assert "airc.exe.sha256" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "airc.exe" in text
    assert "--help" in text
    assert "workflow_dispatch" in text
    assert "setup-python@v5" in text
    assert "python-version: \"3.12\"" in text or "python-version: '3.12'" in text
    assert "pyinstaller" in text.lower()
    assert "provenance.txt" in text
    assert "builder" in text.lower()
    assert "7276" in text
    assert BUILD.is_file()
    # Not a release / MSI / service restart.
    assert "gh release" not in text.lower()
    assert "msiexec" not in text.lower()
    assert "Restart-Service" not in text
    assert "Install-Airc" not in text


def test_fr7276_frozen_common_includes_seal_wire_filexfer():
    frozen = frozen_airc_common_script_paths()
    assert "common/scripts/seal.py" in frozen
    assert "common/scripts/wire.py" in frozen
    assert "common/scripts/filexfer.py" in frozen
    assert "common/scripts/protect.py" in frozen
    assert "common/scripts/crash_report.py" in frozen
    assert "common/scripts/account_map.py" in frozen


def test_fr7276_workflow_paths_cover_frozen_and_airc_glob():
    text = WF.read_text(encoding="utf-8")
    on = _on_block(text)
    pr_paths = _event_block(on, "pull_request")
    push_paths = _event_block(on, "push")
    want = airc_ci_source_paths()
    assert want, "empty airc CI path list"
    for rel in want:
        assert rel in pr_paths, f"airc pull_request path filter missing {rel}"
        assert rel in push_paths, f"airc push path filter missing {rel}"
    assert "airc/**" in pr_paths
    assert "airc/**" in push_paths
    # No blanket common/** that would hide missing frozen pins.
    assert "common/**" not in pr_paths.splitlines() and "\n      - common/**\n" not in ("\n" + pr_paths)
    assert "common/scripts/**" not in pr_paths


def test_fr7276_manifest_json_shape_in_workflow():
    text = WF.read_text(encoding="utf-8")
    assert "source_commit" in text
    assert "exe_sha256" in text
    assert "exe_size_bytes" in text
    assert "Build-Airc.ps1" in text
    # Workflow must verify MANIFEST hash matches the staged exe.
    assert "MANIFEST.json" in text
    assert "exe_sha256" in text
    assert "throw" in text and "MANIFEST" in text


def test_fr7276_build_script_owns_pyinstaller_and_smoke():
    build = BUILD.read_text(encoding="utf-8")
    assert "PyInstaller" in build
    assert "--help" in build
    assert "--selftest" in build
    assert "airc.exe" in build


def test_fr7276_airc_ops_ci_note_has_no_bel():
    """MRB #7284: docs used PowerShell `\\a` so `airc` became ASCII BEL."""
    raw = (ROOT / "airc" / "docs" / "airc-ops.md").read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    assert "\x07" not in text
    assert "FR #7276" in text
    assert "build-airc.yml" in text
    assert "airc.exe" in text
    assert "MANIFEST.json" in text
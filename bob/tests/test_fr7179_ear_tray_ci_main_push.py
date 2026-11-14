"""FR #7179: ear + tray CI build on push to main; ear builds the checkout tip.

build-bob-ear.yml previously only ran on path-filtered PRs (workflow + manifest)
and hard-pinned behavior files to an old SHA, so main commits could not produce
installable ear artifacts. Tray already pushed on main; this gate locks both.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

EAR_WF = ROOT / ".github" / "workflows" / "build-bob-ear.yml"
TRAY_WF = ROOT / ".github" / "workflows" / "build-bob-tray.yml"
WORKER_WF = ROOT / ".github" / "workflows" / "build-bob-worker.yml"
EAR_BUILD = ROOT / "bob" / "scripts" / "Build-BobEar.ps1"
EAR_DOCS = ROOT / "bob" / "docs" / "bob-ear.md"
TRAY_DOCS = ROOT / "bob" / "docs" / "bob-tray-dialogs.md"

EAR_SOURCE_PATHS = [
    ".github/workflows/build-bob-ear.yml",
    "bob/scripts/Build-BobEar.ps1",
    "common/scripts/irc_agent.py",
    "common/scripts/bobreport.py",
    "common/scripts/opencode_fuel.py",
    "common/scripts/bobiverse_build.py",
    "bob/docs/deploy-pool-monitor-manifest.txt",
    "bob/tests/test_fr7179_ear_tray_ci_main_push.py",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _on_block(text: str) -> str:
    m = re.search(r"(?ms)^on:\n(.*?)(?=^permissions:|^jobs:)", text)
    assert m, "workflow missing on: block"
    return m.group(1)


def test_fr7179_ear_workflow_push_main_and_pr_paths():
    assert EAR_WF.is_file()
    text = _text(EAR_WF)
    on = _on_block(text)
    assert "workflow_dispatch" in on
    assert "pull_request:" in on
    assert "push:" in on
    assert "branches: [main]" in on
    for rel in EAR_SOURCE_PATHS:
        assert rel in on, f"ear path filter missing {rel}"
    assert "runs-on: windows-latest" in text
    assert "Build-BobEar.ps1" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-ear" in text
    assert "provenance.txt" in text
    assert "bob-ear.exe.sha256" in text
    assert "source_commit=" in text
    assert "workflow_commit=" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "persist-credentials: false" in text
    assert EAR_BUILD.is_file()


def test_fr7179_ear_no_hard_behavior_pin():
    """Acceptance: build the checked-out commit; drop Confirm-behavior pin."""
    text = _text(EAR_WF)
    assert "Confirm behavior files match" not in text
    assert re.search(r'\$expected\s*=\s*"[0-9a-f]{40}"', text) is None
    assert "behavior_source_sha=4a7f54f6" not in text
    assert "behavior_source_sha=" not in text
    # Provenance must bind the artifact to the workflow/checkout commit.
    assert "source_commit=$($env:WORKFLOW_COMMIT)" in text
    assert "workflow_commit=$($env:WORKFLOW_COMMIT)" in text
    assert 'if ($head -ne $env:WORKFLOW_COMMIT)' in text


def test_fr7179_tray_workflow_push_main():
    assert TRAY_WF.is_file()
    text = _text(TRAY_WF)
    on = _on_block(text)
    assert "push:" in on
    assert "branches: [main]" in on
    assert "pull_request:" in on
    assert "bob/tray/**" in on
    assert "provenance.txt" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-tray" in text


def test_fr7179_ear_matches_worker_artifact_shape():
    """Hashed artifacts like build-bob-worker.yml (exe, .sha256, provenance)."""
    ear = _text(EAR_WF)
    worker = _text(WORKER_WF)
    for needle in (
        "source_commit=",
        "workflow_commit=",
        "exe_sha256=",
        "exe_size_bytes=",
        "build_time_utc=",
        "manifest.txt",
    ):
        assert needle in ear, f"ear provenance missing {needle}"
        assert needle in worker or needle.replace("manifest.txt", "provenance.txt") in worker


def test_fr7179_docs_list_ci_triggers():
    ear_docs = _text(EAR_DOCS)
    assert "FR #7179" in ear_docs
    assert "build-bob-ear.yml" in ear_docs
    assert "push" in ear_docs.lower()
    assert "provenance" in ear_docs.lower()

    tray_docs = _text(TRAY_DOCS)
    assert "build-bob-tray.yml" in tray_docs
    assert "push" in tray_docs.lower() or "main" in tray_docs

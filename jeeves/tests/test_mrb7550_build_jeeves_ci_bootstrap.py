"""MRB #7550: build-jeeves pytest step bootstraps Get-FileHash + git identity."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

WF = REPO / ".github" / "workflows" / "build-jeeves.yml"
HELPERS = REPO / "common" / "scripts" / "Bobiverse-FetchHelpers.ps1"


def test_mrb7550_workflow_bootstraps_filehash_and_git_before_pytest():
    text = WF.read_text(encoding="utf-8")
    assert "Pytest jeeves/tests (FR #7547)" in text
    # Bootstrap must sit in the pytest step, before python -m pytest.
    step = text[text.index("Pytest jeeves/tests (FR #7547)") :]
    step = step[: step.index("Build jeeves.exe")]
    assert "Import-Module Microsoft.PowerShell.Utility" in step
    assert "Get-FileHash" in step
    assert "git config --global user.email" in step
    assert "git config --global user.name" in step
    assert "PSModuleAutoLoadingPreference" in step
    pytest_i = step.index("python -m pytest")
    assert step.index("Import-Module Microsoft.PowerShell.Utility") < pytest_i
    assert step.index("git config --global user.email") < pytest_i


def test_mrb7550_fetch_helpers_ensure_filehash_command():
    text = HELPERS.read_text(encoding="utf-8")
    assert "function Ensure-BobiverseFileHashCommand" in text
    assert "Microsoft.PowerShell.Utility" in text
    assert "FR #7355" in text or "7355" in text
    # Assert-BobiverseSha256 must call the ensure helper before Get-FileHash.
    fn = text[text.index("function Assert-BobiverseSha256") :]
    assert "Ensure-BobiverseFileHashCommand" in fn

"""FR #1454: CI must run test_fr1150 when gitclaim.py changes."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "pytest-gitclaim.yml"


def test_pytest_gitclaim_workflow_exists():
    assert WF.is_file(), f"missing CI workflow: {WF}"


def test_workflow_gates_gitclaim_and_fr1150():
    text = WF.read_text(encoding="utf-8")
    assert "common/scripts/gitclaim.py" in text
    assert "test_fr1150_resync_paginate.py" in text
    assert "pytest" in text.lower()
    # Must fail the job on red (default pytest non-zero exit).
    assert "pull_request" in text

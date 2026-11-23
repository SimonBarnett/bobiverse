"""FR #9217: pytest-ascii-bom job name stays the required-check context."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fr9217_workflow_job_name_is_pytest_ascii_bom():
    yml = (ROOT / ".github" / "workflows" / "pytest-ascii-bom.yml").read_text(encoding="utf-8")
    assert "name: pytest-ascii-bom" in yml
    assert "jobs:" in yml
    assert "pytest-ascii-bom:" in yml
    assert "FR #9217" in yml
    assert yml[:3] != "\ufeff"


def test_fr9217_evidence_doc_lists_both_required_checks():
    doc = (ROOT / "bob" / "docs" / "fr-9217-pytest-ascii-bom-required.md").read_text(encoding="utf-8")
    assert "conflict-markers" in doc
    assert "pytest-ascii-bom" in doc
    assert "24874680" in doc
    assert doc.encode("utf-8")[:3] != b"\xef\xbb\xbf"

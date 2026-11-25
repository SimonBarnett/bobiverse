"""FR #9881: tip policy note + Prefer (A) writer playbook pins."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "bob" / "docs" / "fr-9881-pytest-ascii-bom-tip-policy.md"
MRB_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
UTF8_NOBOM = ROOT / "common" / "scripts" / "Write-BobiverseUtf8NoBom.ps1"
PS1_ASCII = ROOT / "common" / "scripts" / "Write-BobiversePs1AsciiNoBom.ps1"
WF = ROOT / ".github" / "workflows" / "pytest-ascii-bom.yml"


def test_fr9881_policy_doc_exists_and_pins_soft_and_prefer_a():
    assert DOC.is_file()
    text = DOC.read_text(encoding="utf-8")
    assert text.encode("utf-8")[:3] != b"\xef\xbb\xbf"
    assert "pytest-ascii-bom" in text
    assert "build-jeeves" in text
    assert "tip_may_proceed_soft_ascii_bom" in text
    assert "Write-BobiverseUtf8NoBom" in text
    assert "Write-BobiversePs1AsciiNoBom" in text
    assert "Prefer (A)" in text
    assert "soft" in text.lower()


def test_fr9881_mrb_skill_references_policy():
    skill = MRB_SKILL.read_text(encoding="utf-8")
    assert "FR #9881" in skill
    assert "fr-9881-pytest-ascii-bom-tip-policy" in skill
    assert "tip_may_proceed_soft_ascii_bom" in skill


def test_fr9881_writer_helpers_document_utf8encoding_false():
    utf8 = UTF8_NOBOM.read_text(encoding="utf-8")
    ps1 = PS1_ASCII.read_text(encoding="utf-8")
    assert "UTF8Encoding $false" in utf8 or "UTF8Encoding($false)" in utf8
    assert "9881" in utf8
    assert "9881" in ps1
    assert utf8.encode("utf-8")[:3] != b"\xef\xbb\xbf"
    assert ps1.encode("utf-8")[:3] != b"\xef\xbb\xbf"


def test_fr9881_workflow_mentions_prefer_a_and_soft():
    yml = WF.read_text(encoding="utf-8")
    assert "FR #9881" in yml
    assert "Write-BobiverseUtf8NoBom" in yml
    assert "name: pytest-ascii-bom" in yml

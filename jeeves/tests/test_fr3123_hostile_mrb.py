"""Hostile pins for MRB bobiverse#3123 / FR #3117."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mrb_3123_docs_pins():
    text = (ROOT / "docs" / "mrb-3123.md").read_text(encoding="utf-8")
    assert "intake_allowlist" in text
    assert "repo_not_allowed" in text
    assert "a-search" in text


def test_intake_allowlist_module_exists():
    assert (ROOT / "tools" / "monitor" / "intake_allowlist.py").is_file()
    assert (ROOT / "scripts" / "Test-JeevesMonitorIntakeAllowlist.ps1").is_file()

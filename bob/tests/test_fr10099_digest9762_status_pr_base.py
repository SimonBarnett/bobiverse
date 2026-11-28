"""FR #10099 harvest: Digest #9762 status CI PR base vs Closes on main."""
from __future__ import annotations

from repo_layout import ROOT


def test_fr10099_fr_skill_documents_stacked_tray_status_pr_base():
    skill = (
        ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "9764" in skill
    assert "9763" in skill
    assert "non-default" in skill.lower() or "main" in skill
    assert "Build-BobDialogs" in skill


def test_fr10099_tray_docs_stacked_implement_order():
    docs = (ROOT / "bob" / "docs" / "bob-tray-dialogs.md").read_text(encoding="utf-8")
    assert "FR #10099" in docs or "10099" in docs
    assert "9764" in docs
    assert "main" in docs


def test_fr10099_harvest_log_row():
    log = (ROOT / "common" / "docs" / "skill-harvest-log.md").read_text(
        encoding="utf-8"
    )
    assert "10099" in log
    assert "9764" in log
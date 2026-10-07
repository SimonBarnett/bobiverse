"""MRB tip #3168: stale disk-vs-memory queue reload playbook in jeeves troubleshooting."""
from pathlib import Path

from repo_layout import REPO


def test_troubleshooting_documents_ircjeeves_queue_reload():
    p = REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-troubleshooting" / "SKILL.md"
    text = p.read_text(encoding="utf-8")
    assert "Restart-Service ircJeeves" in text
    assert "queue.json" in text
    assert "stale" in text.lower() or "reload" in text.lower()
    assert "BobIrcd" in text


def test_empty_offer_playbook_disk_vs_chair_check():
    p = REPO / "jeeves" / "docs" / "empty-offer-playbook.md"
    text = p.read_text(encoding="utf-8")
    assert "Restart-Service ircJeeves" in text
    assert "queue.json" in text
    assert "!status" in text or "unaccepted" in text

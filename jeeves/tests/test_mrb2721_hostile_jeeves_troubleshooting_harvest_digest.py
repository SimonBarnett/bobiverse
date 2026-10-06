"""MRB #2721 hostile: jeeves-troubleshooting harvest digest (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JT = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-troubleshooting" / "SKILL.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2721_digest_section_present():
    text = _utf8_no_bom(JT)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2721_callback_7700_health():
    text = _utf8_no_bom(JT)
    assert "Callback / :7700 health" in text
    idx = text.index("Callback / :7700 health")
    window = text[idx : idx + 700]
    assert "/bob/v1/report" in window
    assert "BobIrcd" in window
    assert "digest.lock" in window


def test_mrb2721_idle_seats_empty_offers():
    text = _utf8_no_bom(JT)
    assert "Idle seats and empty offers" in text
    idx = text.index("Idle seats and empty offers")
    window = text[idx : idx + 600]
    assert "offer_focus_top" in window
    assert "clear_seat_doing" in window
    assert "!assign" in window


def test_mrb2721_chair_deploys():
    text = _utf8_no_bom(JT)
    assert "Chair deploys:" in text or "**Chair deploys:**" in text
    idx = text.index("Chair deploys")
    window = text[idx : idx + 500]
    assert "jeeves.exe" in window
    assert "ircJeeves" in window
    assert "BobIrcd" in window


def test_mrb2721_homes_and_digest_files():
    text = _utf8_no_bom(JT)
    assert "Homes and digest files" in text
    idx = text.index("Homes and digest files")
    window = text[idx : idx + 500]
    assert "BOB_DIGEST_HOME" in window or "fleet_digest_home" in window
    assert "pytest-of-*" in window or "setdefault" in window


def test_mrb2721_queue_hygiene():
    text = _utf8_no_bom(JT)
    assert "Queue hygiene:" in text or "**Queue hygiene:**" in text
    idx = text.index("Queue hygiene")
    window = text[idx : idx + 600]
    assert "MERGED" in window or "CLOSED" in window
    assert "author_seat" in window or "fr_done" in window


def test_mrb2721_offer_path_invariants():
    text = _utf8_no_bom(JT)
    assert "Chair offer-path invariants" in text
    idx = text.index("Chair offer-path invariants")
    window = text[idx : idx + 600]
    assert "assign_row" in window
    assert "offer_focus_top" in window
    assert "repo_uat" in window or "SKIP_FR" in window


def test_mrb2721_chair_internals():
    text = _utf8_no_bom(JT)
    assert "Chair internals worth knowing" in text
    idx = text.index("Chair internals worth knowing")
    window = text[idx : idx + 500]
    assert "already_running" in window
    assert "jeeves.exe" in window
    assert "git-claim.lock" in window or "RLock" in window


def test_mrb2721_no_dead_audit_table_path():
    text = _utf8_no_bom(JT)
    assert "harvest-lessons-audit-2026-10-06.md" not in text
    assert "no separate audit table file on main" in text


def test_mrb2721_digest_bullets_complete_lines():
    text = _utf8_no_bom(JT)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    chunk = text[start:]
    bullets = [ln for ln in chunk.splitlines() if ln.startswith("- **")]
    assert len(bullets) >= 7
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln
        assert "orphan" not in ln.lower()

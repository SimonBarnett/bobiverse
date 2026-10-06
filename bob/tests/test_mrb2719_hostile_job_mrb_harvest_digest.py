"""MRB #2719 hostile: job-mrb harvest digest lessons (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"


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


def test_mrb2719_digest_section_present():
    text = _utf8_no_bom(MRB)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2719_self_mrb_per_seat_not_machine():
    text = _utf8_no_bom(MRB)
    assert "Self-MRB is per seat, not per machine" in text
    idx = text.index("Self-MRB is per seat, not per machine")
    window = text[idx : idx + 700]
    assert "reason=self-MRB" in window
    assert "sibling seat" in window
    assert "FRW" in window or "author_seat" in window


def test_mrb2719_reoffered_already_merged_mrb():
    text = _utf8_no_bom(MRB)
    assert "Re-offered or already-merged MRB" in text
    idx = text.index("Re-offered or already-merged MRB")
    window = text[idx : idx + 600]
    assert "origin/main" in window
    assert "Do not merge again" in window or "docs/mrb-N" in window


def test_mrb2719_conflicting_or_superseded():
    text = _utf8_no_bom(MRB)
    assert "CONFLICTING or superseded heads" in text
    idx = text.index("CONFLICTING or superseded heads")
    window = text[idx : idx + 700]
    assert "FAIL-superseded" in window or "force-merge" in window
    assert "skill-harvest-log" in window or "keep both" in window or "keeping both" in window


def test_mrb2719_pre_merge_hygiene():
    text = _utf8_no_bom(MRB)
    assert "Pre-merge hygiene gates" in text
    idx = text.index("Pre-merge hygiene gates")
    window = text[idx : idx + 600]
    assert "check_conflict_markers" in window
    assert "body-file" in window or "UTF-8" in window or "BOM" in window


def test_mrb2719_hostile_tests_product_first():
    text = _utf8_no_bom(MRB)
    assert "Hostile tests:" in text or "**Hostile tests:**" in text
    idx = text.index("Hostile tests")
    window = text[idx : idx + 500]
    assert "docs/mrb-N" in window
    assert "assign_row" in window or "behavioural" in window or "behavioral" in window


def test_mrb2719_verdict_boards_not_fr():
    text = _utf8_no_bom(MRB)
    assert "Verdict boards are not FR work" in text
    idx = text.index("Verdict boards are not FR work")
    window = text[idx : idx + 500]
    assert "mrb-pass" in window
    assert "mrb-home" in window
    assert "mrb-fail" in window


def test_mrb2719_prove_the_claim_literally():
    text = _utf8_no_bom(MRB)
    assert "Prove the claim literally" in text
    idx = text.index("Prove the claim literally")
    window = text[idx : idx + 500]
    assert "on_offer" in window or "on_ack" in window
    assert "routing" in window.lower() or "empty labels" in window


def test_mrb2719_audit_table_path_present():
    text = _utf8_no_bom(MRB)
    assert "harvest-lessons-audit-2026-10-06.md" in text
    assert "no separate audit table file on main" not in text


def test_mrb2719_digest_bullets_complete_lines():
    text = _utf8_no_bom(MRB)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    chunk = text[start:]
    bullets = [ln for ln in chunk.splitlines() if ln.startswith("- **")]
    assert len(bullets) >= 7
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln or "receipt" in ln
        assert "orphan" not in ln.lower()

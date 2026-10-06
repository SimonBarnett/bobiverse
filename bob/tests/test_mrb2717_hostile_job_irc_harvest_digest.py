"""MRB #2717 hostile: job-irc harvest digest lessons (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IRC = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"


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


def test_mrb2717_digest_section_present():
    text = _utf8_no_bom(IRC)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2717_needs_mrb1_dead_label_rule():
    text = _utf8_no_bom(IRC)
    assert "needs-mrb1" in text
    assert "needs-human" in text
    assert "hallucinated" in text or "dead" in text
    # Contiguous: obsolete GIVEUP-for-needs-mrb1 guidance is called out
    assert "obsolete" in text
    idx = text.index("needs-mrb1")
    window = text[idx : idx + 400]
    assert "needs-human" in window


def test_mrb2717_umbrellas_living_fr_giveup():
    text = _utf8_no_bom(IRC)
    assert "Umbrellas, living FRs and loops" in text
    assert "ACK then GIVEUP" in text
    assert "never `Closes` a living FR" in text or "never Closes a living FR" in text
    assert "Refs-only" in text or "living architecture" in text


def test_mrb2717_host_pinned_digest_id_fold():
    text = _utf8_no_bom(IRC)
    assert "Host-pinned work" in text
    assert "require_machine=" in text
    assert "DIGEST_ID_FOLD" in text
    # ionos fleet host fold must stay contiguous with the never-GIVEUP-for-literal-name rule
    assert "win-mpre8vi4u6u" in text
    idx = text.index("DIGEST_ID_FOLD")
    window = text[max(0, idx - 80) : idx + 200]
    assert "ionos" in window
    assert "never GIVEUP" in window or "never GIVEUP there" in text


def test_mrb2717_audit_table_path_present():
    text = _utf8_no_bom(IRC)
    assert "harvest-lessons-audit-2026-10-06.md" in text


def test_mrb2717_digest_bullets_complete_lines():
    """Skill/docs hygiene: digest bullets must be complete (no orphan continuation)."""
    text = _utf8_no_bom(IRC)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    chunk = text[start:]
    # next major heading would end the section; take until EOF if last
    lines = chunk.splitlines()
    bullets = [ln for ln in lines if ln.startswith("- **")]
    assert len(bullets) >= 3
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln
        assert "orphan" not in ln.lower()

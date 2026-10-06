"""MRB #2718 hostile: job-fr harvest digest lessons (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"


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


def test_mrb2718_digest_section_present():
    text = _utf8_no_bom(FR)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2718_reoffered_already_covered_fr():
    text = _utf8_no_bom(FR)
    assert "Re-offered or already-covered FR" in text
    assert "Never open a second implement PR" in text
    idx = text.index("Re-offered or already-covered FR")
    window = text[idx : idx + 700]
    assert "DONE with that PR URL" in window or "DONE with that" in window
    assert "Closes" in window


def test_mrb2718_greenfield_product_frs():
    text = _utf8_no_bom(FR)
    assert "Greenfield product FRs" in text
    idx = text.index("Greenfield product FRs")
    window = text[idx : idx + 500]
    assert "VISION" in window
    assert "foundation" in window
    assert "secrets" in window.lower() or "customer keys" in window


def test_mrb2718_closes_vs_refs_living():
    text = _utf8_no_bom(FR)
    assert "Closes vs Refs" in text
    idx = text.index("Closes vs Refs")
    window = text[idx : idx + 500]
    assert "Refs" in window
    assert "living" in window.lower() or "multi-WP" in window
    assert "closingIssuesReferences" in window or "unrelated" in window


def test_mrb2718_test_harness_gotchas():
    text = _utf8_no_bom(FR)
    assert "Test harness gotchas" in text
    idx = text.index("Test harness gotchas")
    window = text[idx : idx + 500]
    assert "registered_machines" in window
    assert "repo_layout" in window or "PYTHONPATH" in window or "sparse" in window


def test_mrb2718_no_dead_audit_table_path():
    text = _utf8_no_bom(FR)
    assert "harvest-lessons-audit-2026-10-06.md" not in text
    assert "no separate audit table file on main" in text


def test_mrb2718_digest_bullets_complete_lines():
    """Skill/docs hygiene: digest bullets must be complete (no orphan continuation)."""
    text = _utf8_no_bom(FR)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    chunk = text[start:]
    lines = chunk.splitlines()
    bullets = [ln for ln in lines if ln.startswith("- **")]
    assert len(bullets) >= 4
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln
        assert "orphan" not in ln.lower()

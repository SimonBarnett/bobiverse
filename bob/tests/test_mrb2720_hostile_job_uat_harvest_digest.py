"""MRB #2720 hostile: job-uat harvest digest lessons (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UAT = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-uat" / "SKILL.md"


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


def test_mrb2720_digest_section_present():
    text = _utf8_no_bom(UAT)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2720_self_uat_forbidden_per_seat():
    text = _utf8_no_bom(UAT)
    assert "Self-UAT is forbidden per seat" in text
    idx = text.index("Self-UAT is forbidden per seat")
    window = text[idx : idx + 600]
    assert "GIVEUP" in window
    assert "self-PASS" in window or "different seat" in window
    assert "mrb-*-fix" in window or "MRB seat" in window


def test_mrb2720_uat_repo_level_only():
    text = _utf8_no_bom(UAT)
    assert "UAT is repo-level only" in text
    idx = text.index("UAT is repo-level only")
    window = text[idx : idx + 600]
    assert "repo_uat" in window
    assert "#0" in window
    assert "GIVEUP" in window
    assert "gh pr list" in window or "open-issue" in window


def test_mrb2720_product_cookbook_release_uat():
    text = _utf8_no_bom(UAT)
    assert "Product, cookbook and release UAT" in text
    idx = text.index("Product, cookbook and release UAT")
    window = text[idx : idx + 700]
    assert "Pack-BobiverseRelease" in window or "Assert-BobiverseReleaseAssets" in window
    assert "gh release create" in window
    assert "VERSION" in window or "FAIL" in window


def test_mrb2720_no_dead_audit_table_path():
    text = _utf8_no_bom(UAT)
    assert "harvest-lessons-audit-2026-10-06.md" not in text
    assert "no separate audit table file on main" in text


def test_mrb2720_digest_bullets_complete_lines():
    text = _utf8_no_bom(UAT)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    chunk = text[start:]
    bullets = [ln for ln in chunk.splitlines() if ln.startswith("- **")]
    assert len(bullets) >= 3
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln
        assert "orphan" not in ln.lower()

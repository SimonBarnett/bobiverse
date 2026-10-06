"""MRB #2765 hostile: complementary digests tip in job-mrb; audit path keep-if-present."""
from __future__ import annotations

from pathlib import Path

JOB_MRB = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-mrb"
    / "SKILL.md"
)
HARVEST = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
    / "SKILL.md"
)
AUDIT = (
    Path(__file__).resolve().parents[2]
    / "common"
    / "docs"
    / "harvest-lessons-audit-2026-10-06.md"
)


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


def test_mrb2765_complementary_digests_under_harvest_digest():
    text = _utf8_no_bom(JOB_MRB)
    assert "**Complementary digests" in text
    idx = text.index("**Complementary digests")
    window = text[idx : idx + 420]
    assert "Self-MRB" in window and "CONFLICTING" in window
    assert "PASS" in window and "docs/mrb-N" in window
    assert "FAIL-duplicate" in window or "not FAIL" in window
    assert "2765" in window or "2719" in window
    digest = text.index("## Harvest digest")
    self_mrb = text.index("- **Self-MRB is per seat", digest)
    assert digest < idx < self_mrb


def test_mrb2765_digest_audit_path_keep_when_present():
    text = _utf8_no_bom(JOB_MRB)
    assert AUDIT.is_file(), "audit table must exist on tip for keep-if-present rule"
    idx = text.index("**Digest audit path")
    window = text[idx : idx + 480]
    assert "exists on the tip" in window or "missing" in window
    assert "docs/mrb-N" in window
    assert "The per-lesson table is in" in text


def test_mrb2765_harvest_lacks_complementary_raw_bullet():
    text = _utf8_no_bom(HARVEST)
    assert "- FR #2705 job-mrb audit digest bullets that restate" not in text
    assert "**Complementary digests" not in text

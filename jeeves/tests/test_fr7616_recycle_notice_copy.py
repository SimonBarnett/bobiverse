"""FR #7616: no_eligible_reviewer recycle notice says live eligible idle seat."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"


def test_fr7616_notice_and_docstring_drop_idle_author_copy():
    src = GITCLAIM.read_text(encoding="utf-8")
    start = src.index("def maybe_recycle_stuck_no_eligible_reviewer")
    end = src.index("\ndef heal_mrb_reviewer_deadlock", start)
    body = src[start:end]
    assert "live eligible idle seat" in body
    assert "idle author, fewest commits" not in body
    assert "least-touched idle author" not in body
    assert "_live_eligible_idle_reviewer" in body
    banned = ("wal" + "rus", "red" + "queen", "ion" + "os", "flam" + "ingo")
    low = body.lower()
    for name in banned:
        assert name not in low

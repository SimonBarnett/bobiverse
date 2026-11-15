"""FR #7631: chair_health no_eligible recycle comment matches live-eligible pick."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAIR = ROOT / "common" / "scripts" / "chair_health.py"


def test_fr7631_comment_drops_idle_author_fewest_commits():
    src = CHAIR.read_text(encoding="utf-8")
    assert "maybe_recycle_stuck_no_eligible_reviewer" in src
    # Locate the call site comment.
    idx = src.index("maybe_recycle_stuck_no_eligible_reviewer")
    chunk = src[max(0, idx - 200) : idx + 80]
    assert "live eligible idle seat" in chunk
    assert "idle author with the fewest commits" not in chunk
    assert "fewest commits" not in chunk
    banned = ("wal" + "rus", "red" + "queen", "ion" + "os", "flam" + "ingo")
    low = chunk.lower()
    for name in banned:
        assert name not in low

def test_mrb7632_comment_cites_live_eligible_fr_chain():
    """MRB hostile: call-site comment must cite the live-eligible FR chain."""
    src = CHAIR.read_text(encoding="utf-8")
    idx = src.index("maybe_recycle_stuck_no_eligible_reviewer")
    chunk = src[max(0, idx - 200) : idx]
    assert "#7574" in chunk or "#7616" in chunk or "#7631" in chunk
    assert "FR #7334" in chunk

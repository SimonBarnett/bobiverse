"""FR #6841: vision inventory matches landed S4 token graph (PR #6823)."""
from pathlib import Path

VISION = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "vision-cli-token-compare-2026-11-12.md"
)


def test_fr6841_inventory_not_no_token_graph():
    raw = VISION.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    start = text.index("## Already on origin/main")
    end = text.index("## Out of scope")
    inv = text[start:end]
    assert "No token graph" not in inv
    assert "FR #6784" in inv or "by-model" in inv.lower() or "by_model" in inv
    assert "/status" in inv

"""FR #6848: vision inventory matches landed FR #6816 butler on login HTML."""
from pathlib import Path

VISION = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "vision-cli-token-compare-2026-11-12.md"
)


def test_fr6848_inventory_login_has_butler():
    raw = VISION.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    start = text.index("## Already on origin/main")
    end = text.index("## Out of scope")
    inv = text[start:end]
    # Old inventory forbade the graphic after FR #6816 / PR #6836 landed it.
    assert "It has no butler image" not in inv
    assert "no butler image" not in inv.lower()
    assert "jeeves-butler.ico" in inv
    assert "6816" in inv or "_render_login_html" in inv

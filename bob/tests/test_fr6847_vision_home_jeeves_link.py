"""FR #6847: vision inventory matches landed S5 home href=/jeeves (PR #6837)."""
from pathlib import Path

VISION = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "vision-cli-token-compare-2026-11-12.md"
)


def test_fr6847_inventory_has_home_jeeves_link():
    raw = VISION.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    start = text.index("## Already on origin/main")
    end = text.index("## Out of scope")
    inv = text[start:end]
    assert "no `/jeeves` link yet" not in inv
    assert "href=\"/jeeves\"" in inv or "href=/jeeves" in inv or "FR #6818" in inv

"""FR #6849: vision inventory matches landed FR #6821 appliance doc URL."""
from pathlib import Path

VISION = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "vision-cli-token-compare-2026-11-12.md"
)


def test_fr6849_inventory_appliance_doc_bob_ntsa_uk():
    raw = VISION.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    start = text.index("## Already on origin/main")
    end = text.index("## Out of scope")
    inv = text[start:end]
    assert "appliance doc still says not to publish the UI on bob.ntsa.uk" not in inv
    assert "FR #6821" in inv or "https://bob.ntsa.uk/jeeves" in inv

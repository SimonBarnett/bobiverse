"""FR #7281: jeeves VISION names public /jeeves front door vs LAN :7701."""
from __future__ import annotations

from pathlib import Path

VISION = Path(__file__).resolve().parents[1] / "VISION.md"


def _text() -> str:
    raw = VISION.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    return raw.decode("utf-8")


def test_fr7281_vision_drops_never_expose_via_bob_ntsa_uk():
    text = _text()
    low = text.lower()
    assert "never expose settings via bob.ntsa.uk" not in low
    assert "never via bob.ntsa.uk" not in low
    assert "never public / never via bob.ntsa.uk" not in low


def test_fr7281_vision_public_jeeves_vs_lan_7701():
    text = _text()
    screens = text.split("## Screens", 1)[1].split("## LOCKED", 1)[0]
    assert "https://bob.ntsa.uk/jeeves" in screens
    assert "7274" in screens
    assert ":7701" in screens or "7701" in screens
    assert "Cloudflare" in screens
    assert "set/unset" in screens or "set / unset" in screens
    locked = text.split("## LOCKED", 1)[1].split("## UNKNOWN", 1)[0]
    assert "https://bob.ntsa.uk/jeeves" in locked
    assert "7701" in locked
    assert "Cloudflare" in locked
    assert "set/unset" in locked or "set / unset" in locked

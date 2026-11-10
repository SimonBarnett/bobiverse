"""FR #6456: VISION Screens/LOCKED name bob.ntsa.uk static webhook docs (FR #6453)."""
from __future__ import annotations

from pathlib import Path


def test_fr6456_vision_screens_names_bob_ntsa_webhook_docs():
    vision = Path(__file__).resolve().parents[1] / "VISION.md"
    text = vision.read_text(encoding="utf-8")
    assert "## Screens" in text
    assert "bob.ntsa.uk" in text
    assert "6453" in text
    assert "jeeves/www/irc-ntsa" in text or "irc-ntsa" in text
    # Screens must mention static webhook/API docs (not only appliance "never via bob.ntsa.uk").
    screens = text.split("## Screens", 1)[1].split("## LOCKED", 1)[0]
    assert "webhook" in screens.lower() and "doc" in screens.lower()
    assert "\x07" not in text and "\x08" not in text


def test_fr6456_vision_locked_bullet():
    vision = (Path(__file__).resolve().parents[1] / "VISION.md").read_text(encoding="utf-8")
    locked = vision.split("## LOCKED", 1)[1].split("## UNKNOWN", 1)[0]
    assert "6453" in locked
    assert "bob.ntsa.uk" in locked

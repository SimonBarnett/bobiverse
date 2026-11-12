"""FR #6785 / FR-005: jeeves VISION Shape names appliance status as a chair companion."""
from __future__ import annotations

from pathlib import Path

VISION = Path(__file__).resolve().parents[1] / "VISION.md"


def _shape() -> str:
    text = VISION.read_text(encoding="utf-8")
    start = text.index("## Shape")
    end = text.index("## Stack")
    return text[start:end]


def test_vision_utf8_no_bom():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "\ufffd" not in raw.decode("utf-8")


def test_shape_primary_stays_service():
    shape = _shape()
    assert "Primary (one): service" in shape


def test_hybrid_names_appliance_status_companion():
    shape = _shape()
    assert "Hybrid note:" in shape
    assert "ircJeeves" in shape
    assert "appliance status" in shape.lower()
    assert "companion" in shape.lower()
    # Must not deny the shipped status page as "not a website"
    assert "(not a website)" not in shape

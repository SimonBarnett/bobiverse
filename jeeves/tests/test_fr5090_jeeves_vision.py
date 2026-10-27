"""FR #5090: jeeves/VISION.md exists for MRB/UAT vision-first judgement (bob/airc parity)."""
from __future__ import annotations

from pathlib import Path

VISION = Path(__file__).resolve().parents[1] / "VISION.md"


def _text() -> str:
    return VISION.read_text(encoding="utf-8")


def test_vision_file_exists_utf8_no_bom():
    assert VISION.is_file(), f"missing {VISION} (FR #5090)"
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "\ufffd" not in raw.decode("utf-8")
    # ASCII-friendly punctuation for WinPS / pin gates (FR #3391 / #3935 class)
    assert "\u2014" not in raw.decode("utf-8")  # em-dash


def test_vision_required_sections():
    text = _text()
    for h in (
        "## Objective",
        "## Success",
        "## Shape",
        "## Stack",
        "## Architecture",
        "## LOCKED",
        "## UNKNOWN",
    ):
        assert h in text, f"missing {h}"
    assert text.count("LOCKED") >= 4


def test_vision_success_rows_cover_chair_ask():
    text = _text()
    assert "| S1 |" in text and "| S5 |" in text
    # Ask: chair present, auto-offer / !bored, recycle give-up exact nick, needs_human, harvest
    assert "ircJeeves" in text or "Jeeves" in text
    assert "!bored" in text or "auto-offer" in text.lower()
    assert "giveup" in text.lower() or "give-up" in text.lower() or "GIVEUP" in text
    assert "needs_human" in text or "needs-human" in text
    assert "FR #5088" in text  # exact-seat give-up after recycle
    assert "FR #4336" in text  # needs_human global auto-offer gate
    assert "harvest" in text.lower()


def test_vision_locked_pins_cast_iron():
    locked = _text()
    locked = locked[locked.index("## LOCKED") : locked.index("## UNKNOWN")]
    assert "Ergo" in locked or "BobIrcd" in locked
    assert "harvest" in locked.lower()
    assert "ircJeeves" in locked
    assert "exact" in locked.lower()  # exact-seat give-up


def test_vision_cites_fr5090_and_fleet_umbrella():
    text = _text()
    assert "FR #5090" in text
    assert "common/docs/vision.md" in text or "Fleet umbrella" in text

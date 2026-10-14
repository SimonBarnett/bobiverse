"""FR #4158: airc/VISION.md exists with measurable Success / LOCKED shape (bob parity FR #1615)."""
from __future__ import annotations

from pathlib import Path

VISION = Path(__file__).resolve().parents[1] / "VISION.md"


def _text() -> str:
    return VISION.read_text(encoding="utf-8")


def test_vision_file_exists_utf8_no_bom():
    assert VISION.is_file()
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


def test_vision_success_rows_cover_ask():
    text = _text()
    assert "| S1 |" in text and "| S5 |" in text
    # Ask: console, shop/wonderland, MSI/client vs workstation, remote shell, harvest
    assert "Airc" in text
    assert "wonderland" in text.lower()
    assert "FR #3834" in text
    assert "shell" in text.lower() or "DONE id=" in text
    assert "AppParameters" in text or "FR #1552" in text
    assert "harvest" in text.lower()
    assert "client" in text.lower() or "workstation" in text.lower()


def test_vision_locked_pins_cast_iron():
    locked = _text()
    locked = locked[locked.index("## LOCKED") : locked.index("## UNKNOWN")]
    assert "Ergo" in locked or "BobIrcd" in locked
    assert "harvest" in locked.lower()
    assert "{MachineId}_console" in locked or "{mid}_console" in locked or "_console" in locked
    assert "AircConsole" in locked  # one-console rule cites the leftover name


def test_vision_cites_fr4158_and_fleet_umbrella():
    text = _text()
    assert "FR #4158" in text
    assert "common/docs/vision.md" in text or "Fleet umbrella" in text

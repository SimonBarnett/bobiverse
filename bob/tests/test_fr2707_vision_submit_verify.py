"""FR #2707: bob/VISION.md S3 + architecture cite submit-verify (FR #2696)."""
from __future__ import annotations

from pathlib import Path

VISION = Path(__file__).resolve().parents[1] / "VISION.md"


def test_vision_s3_mentions_submit_verify_and_fr2696():
    text = VISION.read_text(encoding="utf-8")
    assert "| S3 |" in text
    # how-measured cites durable fix, not only gap + double Enter
    assert "submit-verify" in text
    assert "FR #2696" in text
    assert "never re-paste" in text or "Enter-only" in text
    assert "test_fr2696_inject_submit_verify.py" in text


def test_vision_architecture_relay_mentions_submit_verify():
    text = VISION.read_text(encoding="utf-8")
    # Architecture fence line for relay
    assert "submit-verify" in text
    idx = text.index("## Architecture")
    arch = text[idx : text.index("## Screens")]
    assert "submit-verify" in arch
    assert "FR #2696" in arch


def test_vision_utf8_no_bom_after_edit():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")

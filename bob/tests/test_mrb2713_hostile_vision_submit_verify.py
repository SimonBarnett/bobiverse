"""Hostile MRB #2713: VISION S3/architecture/LOCKED must pin submit-verify (FR #2707/#2696)."""
from __future__ import annotations

from pathlib import Path

VISION = Path(__file__).resolve().parents[1] / "VISION.md"


def _s3_row() -> str:
    for ln in VISION.read_text(encoding="utf-8").splitlines():
        if ln.startswith("| S3 |"):
            return ln
    raise AssertionError("S3 row missing")


def test_mrb2713_s3_intent_still_no_manual_enter():
    row = _s3_row()
    assert "no manual Enter" in row
    assert "submit-verify" in row
    assert "FR #2696" in row
    assert "test_fr2696_inject_submit_verify.py" in row
    assert "never re-paste" in row or "Enter-only" in row


def test_mrb2713_s3_fail_when_cites_submit_verify_outcome():
    row = _s3_row()
    assert "submit-verify ok" in row or "retries exhausted" in row
    assert "relay: injected" in row


def test_mrb2713_architecture_relay_enter_only_retry():
    text = VISION.read_text(encoding="utf-8")
    arch = text[text.index("## Architecture") : text.index("## Screens")]
    relay = next(ln for ln in arch.splitlines() if "relay:" in ln)
    assert "submit-verify" in relay
    assert "Enter-only" in relay or "Enter-only retry" in relay
    assert "FR #2696" in relay
    assert "gap" in relay.lower() or "Enter" in relay


def test_mrb2713_locked_mentions_submit_verify_env():
    text = VISION.read_text(encoding="utf-8")
    locked = text[text.index("## LOCKED") : text.index("## UNKNOWN")]
    assert "submit-verify" in locked
    assert "BOB_WORKER_SUBMIT_VERIFY" in locked
    assert "never re-paste" in locked or "Enter-only" in locked


def test_mrb2713_vision_utf8_box_drawing_intact():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "\ufffd" not in text
    assert "outbox.txt" in text and "agent ACK" in text

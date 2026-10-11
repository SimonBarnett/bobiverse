"""Hostile pins for MRB #4148 / FR #4128 (VISION S3 + FR #4115 post-FAILED recovery)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

VISION = ROOT / "bob/VISION.md"


def _s3() -> str:
    for ln in VISION.read_text(encoding="utf-8").splitlines():
        if ln.startswith("| S3 |"):
            return ln
    raise AssertionError("S3 missing")


def test_mrb4148_s3_keeps_2696_and_adds_4115():
    row = _s3()
    assert "FR #2696" in row and "FR #4115" in row
    assert "never re-paste" in row
    assert "verify" in row.lower()
    assert "FAILED" in row or "failed" in row.lower()
    assert "re-paste" in row.lower()
    assert "inject failed" in row.lower() or "NACK" in row
    assert "test_fr4115_inject_recovery.py" in row


def test_mrb4148_locked_and_architecture_contiguous():
    text = VISION.read_text(encoding="utf-8")
    locked = text[text.index("## LOCKED") : text.index("## UNKNOWN")]
    assert "never re-paste inside the verify loop" in locked
    assert "FR #4115" in locked and "FR #2696" in locked
    arch = text[text.index("## Architecture") : text.index("## Screens")]
    assert "FR #4115" in arch
    assert "never re-paste inside verify loop" in arch or "Enter-only retry never re-paste" in arch


def test_mrb4148_vision_utf8_no_bom():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    assert "\ufffd" not in raw.decode("utf-8")

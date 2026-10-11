"""FR #4128: VISION S3 documents FR #4115 post-FAILED re-paste-once without weakening Enter-only (FR #2696)."""
from __future__ import annotations

from pathlib import Path

VISION = Path(__file__).resolve().parents[1] / "VISION.md"


def _s3_row() -> str:
    for ln in VISION.read_text(encoding="utf-8").splitlines():
        if ln.startswith("| S3 |"):
            return ln
    raise AssertionError("S3 row missing")


def test_s3_keeps_enter_only_never_re_paste_in_verify_loop():
    row = _s3_row()
    assert "FR #2696" in row
    assert "Enter-only" in row or "never re-paste" in row
    # Must not drop the verify-loop Enter-only rule when adding #4115.
    assert "verify" in row.lower()
    assert "never re-paste" in row or "Enter-only retry never re-paste" in row


def test_s3_documents_fr4115_post_failed_re_paste_once():
    row = _s3_row()
    assert "FR #4115" in row
    assert "re-paste" in row.lower() or "repaste" in row.lower()
    assert "FAILED" in row or "failed" in row.lower()
    assert "NACK" in row or "inject failed" in row.lower()
    assert "test_fr4115_inject_recovery.py" in row


def test_s3_fail_when_mentions_inject_failed_nack():
    row = _s3_row()
    fail = row.split("|")[-2] if row.count("|") >= 5 else row
    assert "inject failed" in fail.lower() or "NACK" in fail or "lost paste" in fail.lower()


def test_architecture_and_locked_cite_4115_recovery():
    text = VISION.read_text(encoding="utf-8")
    arch = text[text.index("## Architecture") : text.index("## Screens")]
    assert "FR #4115" in arch or "re-paste" in arch.lower()
    locked = text[text.index("## LOCKED") : text.index("## UNKNOWN")]
    assert "FR #4115" in locked
    assert "Enter-only" in locked or "never re-paste" in locked
    assert "FR #2696" in locked


def test_vision_utf8_no_bom():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "\ufffd" not in raw.decode("utf-8")

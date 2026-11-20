"""FR #8388: OpenCode submit-verify docs match FR #8270 turn-receipt rule."""
from pathlib import Path

from repo_layout import ROOT

WORKER = ROOT / "bob" / "docs" / "bob-worker.md"
INJECT = ROOT / "bob" / "docs" / "fr" / "opencode-seat-gaps" / "FR-OC-INJECT.md"


def test_fr8388_docs_name_turn_receipt_not_enter_retries() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    inject = INJECT.read_text(encoding="utf-8")
    for text in (worker, inject):
        assert "turn_started" in text
        assert "opencode-turns.jsonl" in text
        assert "do not send Enter" in text or "retries do not send Enter" in text
        assert "probe=spawn kind=opencode" in text
        assert "probe=no turn receipt kind=opencode" in text
    assert "Cursor and Grok stay bare" in worker
    assert "inject failed" not in inject
    assert not WORKER.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not INJECT.read_bytes().startswith(b"\xef\xbb\xbf")

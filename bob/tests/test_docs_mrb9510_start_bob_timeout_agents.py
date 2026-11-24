"""docs/mrb-9510: AGENTS.md documents Start-Bob sync timeout (FR #9508)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

AGENTS = ROOT / "bob" / "AGENTS.md"


def test_agents_documents_bob_start_sync_timeout():
    raw = AGENTS.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "BOB_START_SYNC_TIMEOUT_SEC" in text
    assert "FR #9508" in text or "PR #9510" in text
    assert "out of process" in text.lower() or "out-of-process" in text.lower()
    assert "bob-ear" in text.lower()
    assert "BOBIVERSE_NO_UPDATE" in text

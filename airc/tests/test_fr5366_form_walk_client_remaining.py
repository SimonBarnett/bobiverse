"""FR #5366: client remaining set includes packed form_walk fixture."""
from __future__ import annotations

from repo_layout import ROOT

from test_fr3514_client_allowlist_payload import CLIENT_REMAINING_FILES

ALLOW = ROOT / "airc" / "tests" / "test_fr3514_client_allowlist_payload.py"
FIX = r"airc\priority-worker\fixtures\form_walk.json"


def test_fr5366_form_walk_in_client_remaining():
    assert FIX in CLIENT_REMAINING_FILES
    assert len(CLIENT_REMAINING_FILES) == 33
    t = ALLOW.read_text(encoding="utf-8")
    assert "FR #5366" in t
    assert not ALLOW.read_bytes().startswith(b"\xef\xbb\xbf")

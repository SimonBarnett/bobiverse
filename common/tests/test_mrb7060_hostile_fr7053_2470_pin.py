"""MRB #7060 hostile pin: FR #7053 strengthens 2470 ff-blocked test for park allowlist."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

TEST = REPO / "common" / "tests" / "test_fr2470_sync_behind_alert.py"


def test_mrb7060_fr2470_ff_blocked_pins_skip_not_hotpatch():
    raw = TEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "def test_fr2470_ff_blocked_alerts_with_behind_count" in text
    i = text.index("def test_fr2470_ff_blocked_alerts_with_behind_count")
    body = text[i : i + 3500]
    assert '== "# LOCAL\\n"' in body or '== "# LOCAL\n"' in body
    assert "skip-not-hotpatch" in body
    assert "FR #7053" in body or "FR #7024" in body
    assert "ALERT" in body

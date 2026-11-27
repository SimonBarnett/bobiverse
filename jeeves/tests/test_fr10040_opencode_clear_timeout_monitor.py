"""FR #10040 monitor fingerprint."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "monitor"))

import opencode_clear_timeout as clear_mod  # noqa: E402


def test_fr10040_clear_timeout_and_stale_no_ack():
    text = (
        "opencode finish: Clear result=failed:TimeoutExpired\n"
        "relay: stale worktree offer #812 age_s=295 (no ACK yet)\n"
    )
    fp = clear_mod.scan_log(text, machine="marchhare", nick="marchhare-20008", turns_empty=True)
    assert fp == "opencode_clear_timeout_no_ack:marchhare:marchhare-20008"
    assert clear_mod.scan_log(text, machine="marchhare", nick="n", turns_empty=False) is None
    assert clear_mod.scan_log("Clear result=ok", machine="m", nick="n", turns_empty=True) is None

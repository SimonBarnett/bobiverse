"""FR #10041 monitor fingerprint."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "monitor"))

import opencode_gh_auth_missing as auth_mod  # noqa: E402


def test_fr10041_gh_auth_missing_fingerprint():
    text = "opencode-ready: blocked gh_auth_missing. Next: gh auth login"
    fp = auth_mod.scan_log(text, machine="marchhare", nick="marchhare-4604", seat_online=True)
    assert fp == "opencode_gh_auth_missing:marchhare:marchhare-4604"
    assert auth_mod.scan_log(text, machine="m", nick="n", seat_online=False) is None

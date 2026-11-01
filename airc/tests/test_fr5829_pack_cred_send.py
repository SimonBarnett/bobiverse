"""FR #5829: Pack-AircConsoleRelease stages CRED via=irc sender scripts."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "airc" / "scripts" / "Pack-AircConsoleRelease.ps1"


def test_fr5829_pack_allowlist_includes_cred_send():
    text = PACK.read_text(encoding="utf-8")
    assert "FR #5829" in text or "FR #5825" in text
    for rel in (
        r"scripts\airc_cred_send.py",
        r"scripts\Send-AircCred.ps1",
        r"scripts\airc_cred_irc.py",
    ):
        assert rel in text, rel


def test_fr5829_sender_files_exist_in_repo():
    scripts = ROOT / "airc" / "scripts"
    assert (scripts / "airc_cred_send.py").is_file()
    assert (scripts / "Send-AircCred.ps1").is_file()
    assert (scripts / "airc_cred_irc.py").is_file()

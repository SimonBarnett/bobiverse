"""docs/mrb-5830: Pack staging of CRED via=irc sender is documented."""
from __future__ import annotations

from repo_layout import ROOT

SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
PACK = ROOT / "airc" / "scripts" / "Pack-AircConsoleRelease.ps1"


def test_mrb5830_skill_mentions_pack_staging():
    text = SKILL.read_text(encoding="utf-8")
    assert "Pack staging (FR #5829)" in text
    assert "Pack-AircConsoleRelease.ps1" in text
    assert "airc_cred_send.py" in text
    assert "Send-AircCred.ps1" in text


def test_mrb5830_pack_still_allowlists_sender():
    text = PACK.read_text(encoding="utf-8")
    for rel in (
        r"scripts\airc_cred_send.py",
        r"scripts\Send-AircCred.ps1",
        r"scripts\airc_cred_irc.py",
    ):
        assert rel in text, rel

"""MRB #3757 hostile: FR #3756 Install-AircConsole Ergo PASS env fallbacks."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

INSTALL = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def test_mrb3757_hostile_env_keys_and_clear_error():
    text = INSTALL.read_text(encoding="utf-8")
    assert "FR #3756" in text
    for key in (
        "AIRC_PACK_ERGO_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_SERVER_PASSWORD",
        "BOB_IRC_PASSWORD",
    ):
        assert key in text
    assert "GetEnvironmentVariable" in text
    assert "-ErgoPasswordFile" in text
    assert "Never invent" in text
    assert "Public MSIs never embed" in text or "issue #4" in text


def test_mrb3757_hostile_ascii_and_skill_row():
    raw = INSTALL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert all(b < 128 for b in raw)
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3756" in skill
    assert "AGENTIC_IRC_PASSWORD" in skill or "-ErgoPasswordFile" in skill
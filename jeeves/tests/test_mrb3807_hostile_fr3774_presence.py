"""MRB #3807 hostile: FR #3774 client presence-only JOIN #bobiverse."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"
SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
PIN = ROOT / "airc" / "tests" / "test_fr3774_client_presence_bobiverse.py"


def test_mrb3807_hostile_presence_api_contiguous():
    text = CONSOLE.read_text(encoding="utf-8")
    assert "FR #3774" in text
    assert "def resolve_presence_channels(" in text
    assert "def normalize_irc_channel(" in text
    assert "def same_irc_channel(" in text
    assert 'DEFAULT_CLIENT_PRESENCE_CHANNELS' in text or '"#bobiverse"' in text
    assert "silent_channel" in text
    svc = SERVICE.read_text(encoding="utf-8")
    assert "presence_channels" in svc
    assert "FR #3774" in svc or "same_irc_channel" in svc


def test_mrb3807_hostile_install_docs_skill_pin():
    install = INSTALL.read_text(encoding="utf-8")
    assert "presence_channels" in install
    assert "3774" in install
    post = POST.read_text(encoding="utf-8")
    assert "FR #3774" in post
    assert "presence_channels" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3774" in skill
    assert "presence_channels" in skill
    assert PIN.is_file()
    pin = PIN.read_text(encoding="utf-8")
    assert "FR #3774" in pin
    assert "silent_channel" in pin
    assert "resolve_presence_channels" in pin


def test_mrb3807_hostile_product_pin_ascii_no_bom():
    raw = PIN.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert all(b < 128 for b in raw)

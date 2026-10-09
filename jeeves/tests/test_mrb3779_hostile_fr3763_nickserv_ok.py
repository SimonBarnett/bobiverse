"""MRB #3779 hostile: FR #3763 skip SASL until console.nickserv-ok."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SERVICE = ROOT / "airc" / "scripts" / "airc_console_service.py"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
PIN = ROOT / "airc" / "tests" / "test_fr3763_fresh_console_sasl.py"


def test_mrb3779_hostile_service_nickserv_ok_gate():
    text = SERVICE.read_text(encoding="utf-8")
    assert "FR #3763" in text
    assert "console.nickserv-ok" in text
    assert "_nickserv_account_known" in text
    assert "_mark_nickserv_ok" in text
    assert "skip SASL until NickServ account exists" in text
    # Loud ERROR path only when marker known.
    assert "password mismatch with console.password" in text
    # Hostile: NickServ NOTICE matcher must not use bare "successful" alone.
    assert '"successful",' not in text and "'successful'," not in text
    assert "authentication successful" in text or "sasl authentication successful" in text


def test_mrb3779_hostile_skill_and_product_pin():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3763" in skill
    assert "nickserv-ok" in skill
    assert "FR #3762" in skill  # keep-both after main merge
    assert PIN.is_file()
    pin = PIN.read_text(encoding="utf-8")
    assert "FR #3763" in pin
    assert "console.nickserv-ok" in pin
    assert "fresh_home_skips_sasl" in pin or "skip SASL" in pin


def test_mrb3779_hostile_product_pin_ascii_no_bom():
    raw = PIN.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert all(b < 128 for b in raw)

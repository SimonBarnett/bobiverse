"""MRB #3787 hostile: FR #3764 client update=on vs self-update=off clarity."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"
POST = ROOT / "common" / "docs" / "post-install.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
PIN = ROOT / "airc" / "tests" / "test_fr3764_client_update_cap_clarity.py"


def test_mrb3787_hostile_log_line_remote_not_auto():
    text = CONSOLE.read_text(encoding="utf-8")
    assert "FR #3764" in text
    assert "remote UPDATE; not auto self-update" in text
    assert "ops-gated remote" in text
    # log_line must keep the clarifying parenthetical.
    assert "(remote UPDATE; not auto self-update)" in text


def test_mrb3787_hostile_docs_skill_keep_both():
    post = POST.read_text(encoding="utf-8")
    assert "FR #3764" in post
    assert "ops-gated remote UPDATE" in post or "remote UPDATE" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3764" in skill
    assert "FR #3763" in skill  # keep-both after main merge
    assert "remote UPDATE" in skill
    assert PIN.is_file()


def test_mrb3787_hostile_product_pin_ascii_no_bom():
    raw = PIN.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert all(b < 128 for b in raw)
    pin = PIN.read_text(encoding="utf-8")
    assert "FR #3764" in pin
    assert "remote" in pin.lower()

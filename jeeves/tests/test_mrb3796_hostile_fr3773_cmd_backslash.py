"""MRB #3796 hostile: FR #3773 cmd: trailing backslash via /d /s /c string."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"
DOCS = ROOT / "airc" / "docs" / "airc-remote-control.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
PIN = ROOT / "airc" / "tests" / "test_fr3773_cmd_trailing_backslash.py"


def test_mrb3796_hostile_build_cmd_command_line_present():
    text = CONSOLE.read_text(encoding="utf-8")
    assert "FR #3773" in text
    assert "def build_cmd_command_line(" in text
    assert "def prepare_cmd_body(" in text
    assert '/d /s /c "' in text or "/d /s /c" in text
    # Execution path must use string cmdline for cmd kind.
    assert "args = build_cmd_command_line(req.body or \"\")" in text or (
        "build_cmd_command_line(req.body" in text
    )
    assert "list2cmdline" in text


def test_mrb3796_hostile_docs_skill_and_product_pin():
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #3773" in docs
    assert "list2cmdline" in docs
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3773" in skill
    assert "build_cmd_command_line" in skill
    assert PIN.is_file()
    pin = PIN.read_text(encoding="utf-8")
    assert "FR #3773" in pin
    assert "build_cmd_command_line" in pin


def test_mrb3796_hostile_product_pin_ascii_no_bom():
    raw = PIN.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert all(b < 128 for b in raw)

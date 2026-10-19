"""docs/mrb-4809 hostile pins for FR #4794 / PR #4809."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "scripts" / "airc_console.py"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"


def test_mrb4809_cont_does_not_rerun_and_advances():
    out = ac.ShellOutcome(
        job_id="cafebabe",
        exit_code=0,
        stdout="\n".join(f"R{i}-" + ("Z" * 200) for i in range(90)),
        stderr="",
    )
    p1 = ac.format_shell_replies_ex(out, max_irc_lines=12)
    assert p1.next_offset == 12
    p2 = ac.format_shell_replies_ex(out, offset=12, max_irc_lines=12)
    assert p2.next_offset is not None
    assert [r for r in p1.lines if r.startswith("out ")][0] != [
        r for r in p2.lines if r.startswith("out ")
    ][0]
    assert p1.lines[-1].startswith("DONE id=cafebabe")
    assert p2.lines[-1].startswith("DONE id=cafebabe")


def test_mrb4809_parse_cont_rejects_noise():
    assert ac.parse_cont_request("") is None
    assert ac.parse_cont_request("CONT") is None  # missing id
    assert ac.parse_cont_request("shell id=aabbccdd Get-Date") is None


def test_mrb4809_source_and_skill_pins():
    text = CONSOLE.read_text(encoding="utf-8")
    assert "def continue_replies" in text
    assert "def format_shell_replies_ex" in text
    assert "shell_cont" in text
    assert "FR #4794" in text
    skill = SKILL.read_bytes()
    assert b"\x07" not in skill
    assert "CONT id=" in SKILL.read_text(encoding="utf-8")
    assert "4794" in SKILL.read_text(encoding="utf-8")

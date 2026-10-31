"""FR #5312: LEGION skills and remote-control docs (FR-E)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CMD = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"
TROUBLE = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
REMOTE = ROOT / "airc/docs/airc-remote-control.md"
OPS = ROOT / "airc/docs/airc-ops.md"


def _read(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    return raw.decode("utf-8")


def test_fr5312_commands_skill_legion():
    t = _read(CMD)
    assert "FR #5312" in t
    assert "LEGION" in t
    assert "DCCLISTEN" in t
    assert "PriorityAirc/LegionAdmin" in t
    assert "update=off" in t or "update-disabled" in t
    assert "password=" not in t.lower()
    i = t.find("FR #5312")
    assert "\u2014" not in t[i : i + 700]


def test_fr5312_troubleshooting_and_ops():
    tr = _read(TROUBLE)
    assert "LEGION" in tr
    assert "DCCLISTEN" in tr
    assert "update=off" in tr or "update-disabled" in tr
    assert "password=" not in tr.lower()
    ops = _read(OPS)
    assert "LEGION" in ops
    assert "FR #5312" in ops or "FR #3991" in ops


def test_fr5312_remote_control():
    t = _read(REMOTE)
    assert "LEGION" in t
    assert "DCCLISTEN" in t
    assert "FR #5312" in t or "FR #5308" in t
    assert "password=" not in t.lower()

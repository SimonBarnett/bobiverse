"""FR #5287: skills document built-in Priority Client (S5)."""
from __future__ import annotations

from repo_layout import ROOT

CMD = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
AIRC = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def _check(path):
    raw = path.read_bytes()
    t = path.read_text(encoding="utf-8")
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "CAST IRON RULE" in t
    assert "PRIORITY" in t
    assert "CredMan" in t
    assert "allowlist" in t.lower() or "allow-list" in t.lower()
    assert "prepare" in t.lower()
    assert "password=" not in t.lower()
    low = t.lower()
    assert "do not copy" in low or "without copying" in low or "not a drop" in low or "no agent drop" in low
    assert "m:\\ai\\airc-priority" not in low or "do not" in low
    return t


def test_fr5287_commands_priority_verbs_and_gates():
    t = _check(CMD)
    assert "\u2014" not in t
    assert "PRIORITY connect" in t or "PRIORITY prepare" in t
    assert "PRIVMSG" in t
    assert "REPPREPDIRECT2" in t or "UPD" in t or ".prp" in t


def test_fr5287_airc_skill_points_at_commands():
    t = _check(AIRC)
    assert "bobiverse-airc-commands" in t
    assert "5287" in t or "Priority Client" in t

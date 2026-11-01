"""MRB #5733: NETWORK identity skill table stays two-column; DONE identity pin."""
from __future__ import annotations

from repo_layout import ROOT

SKILL_T = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
SKILL_C = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"


def test_mrb5733_troubleshooting_identity_row_two_columns():
    text = SKILL_T.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "NetworkAdmin" in ln and "auth_failed" in ln)
    assert line.count("|") == 3, line
    assert "identity=" in line or "account=" in line
    assert "5711" in line


def test_mrb5733_commands_network_admin_pin():
    blob = SKILL_C.read_text(encoding="utf-8")
    assert "NetworkAdmin" in blob
    assert "5711" in blob
    assert "LEGION|EXTENSION|NETWORK" in blob or "NETWORK" in blob

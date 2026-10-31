"""FR #5282: skills document UPDATE restart contract, failure intake, VERSION."""
from __future__ import annotations

from repo_layout import ROOT

CMD = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
TS = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
AIRC = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_fr5282_commands_update_contract_and_version():
    t = CMD.read_text(encoding="utf-8")
    raw = CMD.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "CAST IRON RULE" in t
    assert "UPDATE airc" in t
    assert "latest" in t.lower()
    assert "TargetVersion" in t or "pin" in t.lower()
    assert "120s" in t or "120 s" in t
    assert "msiexec" in t.lower()
    assert "5279" in t
    assert "idempotency_key" in t
    assert "VERSION" in t and "airc_ver=" in t
    assert "id=" in t
    assert "password=" not in t.lower()
    assert "\u2014" not in t


def test_fr5282_troubleshooting_failure_intake():
    t = TS.read_text(encoding="utf-8")
    assert "5279" in t
    assert "download-failed" in t or "failure class" in t.lower()
    assert "VERSION" in t
    assert "password=" not in t.lower()


def test_fr5282_airc_skill_cross_link():
    t = AIRC.read_text(encoding="utf-8")
    assert "bobiverse-airc-commands" in t
    assert "5282" in t or "UPDATE airc" in t

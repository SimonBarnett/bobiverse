"""FR #5301: NETWORK diagnostic skills and remote-control docs (FR-D)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CMD = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"
TROUBLE = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
REMOTE = ROOT / "airc/docs/airc-remote-control.md"


def _read(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    return raw.decode("utf-8")


def test_fr5301_commands_skill_network_e2e():
    t = _read(CMD)
    assert "FR #5301" in t
    assert "NETWORK diag" in t
    assert "DCCLISTEN" in t
    assert "UPDATE-class" in t or "update=off" in t
    assert "isolated" in t.lower()
    assert "hostname" in t and "ips" in t and "ou" in t.lower()
    assert "password=" not in t.lower()
    i = t.find("FR #5301")
    assert "\u2014" not in t[i : i + 800]


def test_fr5301_troubleshooting_auth_isolation():
    t = _read(TROUBLE)
    assert "NETWORK" in t
    assert "DCCLISTEN" in t
    assert "update-disabled" in t or "update=off" in t
    assert "isolated" in t.lower()
    assert "password=" not in t.lower()


def test_fr5301_remote_control_table_and_example():
    t = _read(REMOTE)
    assert "`NETWORK" in t or "NETWORK diag" in t
    assert "DCCLISTEN" in t
    assert "FR #5301" in t or "FR #5298" in t
    assert "UPDATE" in t
    assert "password=" not in t.lower()

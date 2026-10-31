"""FR #5294: EXTENSION skills/docs (GPO, fallback, DCC, isolation, default id)."""
from __future__ import annotations

from repo_layout import ROOT

CMD = ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md"
TS = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
AIRC = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
REMOTE = ROOT / "airc/docs/airc-remote-control.md"
EXT_ID = "cgmpadejahkaggjpffnhaoiafbnicgpa"


def _utf8_no_bom_no_emdash(path):
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path.name
    text = raw.decode("utf-8")
    assert "\u2014" not in text, path.name
    return text


def test_fr5294_commands_skill_end_to_end():
    t = _utf8_no_bom_no_emdash(CMD)
    assert "CAST IRON" in t
    assert "EXTENSION" in t
    assert EXT_ID in t
    assert "DCCLISTEN" in t
    assert "Priority-web-extension" in t
    assert "WhatIf" in t
    assert "LDAP" in t or "fill-holes" in t.lower() or "registry" in t.lower()
    assert "isolated" in t.lower()
    assert "password=" not in t.lower()
    assert "update=off" in t or "UPDATE" in t


def test_fr5294_troubleshooting_and_remote():
    ts = TS.read_text(encoding="utf-8")
    assert not TS.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "EXTENSION" in ts
    assert EXT_ID in ts or "ForceInstall" in ts
    rem = REMOTE.read_text(encoding="utf-8")
    assert "EXTENSION" in rem
    assert EXT_ID in rem
    assert "DCCLISTEN" in rem
    airc = AIRC.read_text(encoding="utf-8")
    assert "EXTENSION" in airc
    assert "5294" in airc or "Priority web" in airc

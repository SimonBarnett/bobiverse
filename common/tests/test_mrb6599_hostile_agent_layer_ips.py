"""MRB #6599 hostile pins for FR #6596 agent-layer private IP scrub.

Pins that product PR #6599 landed on main:
- airc bobiverse-airc-commands LEGION WhatIf uses allowlisted 127.0.0.1
- no 10.0.0.8 private LAN literal in that skill
- bob-commands UPDATE status prose avoids secret-shaped 'token: accepted'
"""
from __future__ import annotations

from repo_layout import ROOT

AIRC_CMD = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
BOB_CMD = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-commands" / "SKILL.md"


def test_mrb6599_airc_legion_example_uses_loopback():
    raw = AIRC_CMD.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8")
    assert "LEGION 127.0.0.1 -WhatIf" in t
    assert "10.0.0.8" not in t


def test_mrb6599_bob_commands_avoids_token_colon_accepted():
    raw = BOB_CMD.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8")
    assert "token: accepted" not in t.lower()
    assert "status tokens such as accepted" in t or "UPDATE <status>" in t

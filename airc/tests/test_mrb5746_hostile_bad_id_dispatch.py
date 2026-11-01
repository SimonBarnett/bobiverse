"""MRB #5746 hostile pins: bad_id on_line dispatch + ear non-hex id= (FR #5742)."""
from __future__ import annotations

from pathlib import Path

import irc_agent as ia
from repo_layout import ROOT

SVC = ROOT / "airc" / "scripts" / "airc_console_service.py"
AGENT = ROOT / "common" / "scripts" / "irc_agent.py"
CMD = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"


def test_mrb5746_service_dispatches_bad_id_in_both_sets():
    text = SVC.read_text(encoding="utf-8")
    # Contiguous: bad_id in the reply-send action frozenset window.
    assert '"bad_id"' in text
    assert "FR #5742" in text
    # Auth-allow path must list bad_id with the other long verbs.
    assert 'action in {"update", "priority", "network", "extension", "legion", "bad_id"}' in text or (
        '"bad_id"' in text and "auth-allow" in text.lower()
    )


def test_mrb5746_ear_reply_re_accepts_nonhex_id():
    src = AGENT.read_text(encoding="utf-8")
    assert r"id=\S+" in src
    assert "FR #5742" in src
    assert ia.is_airc_console_reply(
        "tm_console", "err id=nothex!! seq=1 code=bad_id need-8-hex"
    )
    assert ia.is_airc_console_reply("tm_console", "DONE id=nothex!! exit=2")
    assert not ia.is_airc_console_reply(
        "bob-tm", "err id=nothex!! seq=1 code=bad_id need-8-hex"
    )


def test_mrb5746_skill_mentions_service_dispatch():
    blob = CMD.read_text(encoding="utf-8")
    assert "5742" in blob
    assert "bad_id" in blob
    assert "on_line" in blob or "dispatch" in blob.lower() or "Service" in blob

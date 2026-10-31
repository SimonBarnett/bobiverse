"""docs/mrb-5560: hostile pins for bare PRIORITY usage (FR #5533)."""
from __future__ import annotations

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT


def test_mrb5560_skill_usage_phrase():
    skill = (ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(encoding="utf-8")
    assert "FR #5533" in skill
    assert "code=usage" in skill
    assert "bare" in skill.lower() or "unknown sub-verb" in skill.lower()


def test_mrb5560_bare_priority_usage_wire():
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console")
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd PRIORITY")
    assert hr and hr.action == "priority"
    lines = (hr.reply or "").splitlines()
    assert lines[0].startswith("err id=aabbccdd seq=1 code=usage")
    assert lines[-1] == "DONE id=aabbccdd exit=2"
    assert ap.parse_priority_usage("PRIORITY connect x") is None

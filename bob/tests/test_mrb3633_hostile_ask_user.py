"""Hostile pins for MRB #3633 / FR #3623 ask_user_question deny + pending hang."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
from repo_layout import ROOT


def test_mrb3633_agent_launch_disallows_ask_user(tmp_path: Path):
    rd = tmp_path / "run"
    rd.mkdir()
    spec = bw.build_launch(
        "grok",
        "agent",
        str(tmp_path / "cwd"),
        "prompt",
        r"C:\fake\grok.exe",
        rd,
        session_id="11111111-1111-1111-1111-111111111111",
    )
    assert "--disallowed-tools" in spec.argv
    i = spec.argv.index("--disallowed-tools")
    assert spec.argv[i + 1] == "ask_user_question"


def test_mrb3633_plan_launch_allows_ask_user(tmp_path: Path):
    rd = tmp_path / "run"
    rd.mkdir()
    spec = bw.build_launch(
        "grok",
        "plan",
        str(tmp_path / "cwd"),
        "prompt",
        r"C:\fake\grok.exe",
        rd,
        session_id="22222222-2222-2222-2222-222222222222",
    )
    assert "--disallowed-tools" not in spec.argv


def test_mrb3633_rules_text_agent_forbids_ask_user():
    text = bw.rules_text(r"C:\x", "agent")
    assert "ask_user_question" in text
    assert "Never call ask_user_question" in text


def test_mrb3633_watch_enter_then_recycle():
    w = bw.AskUserPendingWatch(pending_s=10.0, enter_grace_s=5.0)
    assert w.tick(5.0, 100.0) is None
    assert w.tick(10.0, 100.0) == "enter"
    assert w.tick(12.0, 103.0) is None
    assert w.tick(12.0, 105.0) == "recycle"


def test_mrb3633_skill_fr3623_contiguous():
    text = (
        ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "**FR #3623 ask_user pending:**" in text
    assert "--disallowed-tools ask_user_question" in text
    assert "ask-user-pending" in text

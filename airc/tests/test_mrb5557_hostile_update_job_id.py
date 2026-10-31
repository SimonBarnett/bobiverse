"""MRB #5557 hostile pins: UPDATE id= framing + capability deny (FR #5532)."""
from __future__ import annotations

import airc_console as ac
from airc_auth_helpers import ops_auth
from airc_console import ConsoleCapabilities
from repo_layout import ROOT


def _core(**kw):
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(
        machine="marchhare", auth=auth, nick="marchhare_console", **kw
    )


def test_mrb5557_split_console_job_id():
    assert ac.split_console_job_id("id=8ddfdad8 UPDATE airc") == (
        "8ddfdad8",
        "UPDATE airc",
    )
    assert ac.split_console_job_id("UPDATE airc") == (None, "UPDATE airc")


def test_mrb5557_shell_off_deny_keeps_job_id():
    core = _core(
        update_scheduler=lambda p, v=None, **k: ac.UpdateScheduleResult(
            True, "current", product=p
        ),
        capabilities=ConsoleCapabilities(shell_mode="off"),
    )
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=11223344 UPDATE airc"
    )
    assert hr and hr.action == "capability_deny"
    assert hr.reply == "DONE id=11223344 exit=126 shell-disabled"


def test_mrb5557_update_off_deny_keeps_job_id():
    core = _core(
        update_scheduler=lambda p, v=None, **k: ac.UpdateScheduleResult(
            True, "current", product=p
        ),
        capabilities=ConsoleCapabilities(update="off"),
    )
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=55667788 UPDATE airc"
    )
    assert hr and hr.action == "capability_deny"
    assert hr.reply == "DONE id=55667788 exit=126 update-disabled"


def test_mrb5557_source_and_skill_pins():
    src = (ROOT / "airc" / "scripts" / "airc_console.py").read_text(encoding="utf-8")
    assert "def split_console_job_id" in src
    assert "FR #5532" in src
    assert "DONE id={qid} exit={exit_code}" in src or "DONE id=" in src
    skill = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "id=<job>" in skill or "id=c25bd00e UPDATE" in skill
    assert "FR #5532" in skill
    assert not (
        ROOT / "airc" / "tests" / "test_fr5532_update_job_id_done.py"
    ).read_bytes().startswith(b"\xef\xbb\xbf")

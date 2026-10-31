"""FR #5532: UPDATE accepts leading id= and replies with id + DONE."""
from __future__ import annotations

import airc_console as ac
from airc_auth_helpers import ops_auth


def _core(**kw):
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(
        machine="marchhare", auth=auth, nick="marchhare_console", **kw
    )


def _sched(product, version=None, **kwargs):
    return ac.UpdateScheduleResult(
        ok=True,
        status="current",
        detail="self-update: check result=current local=1.0.7 latest=1.0.7",
        product=product,
        version=version,
    )


def test_fr5532_parse_accepts_leading_job_id():
    assert ac.parse_update_command("id=8ddfdad8 UPDATE airc") == ("airc", None)
    assert ac.parse_update_command("id=8ddfdad8 UPDATE airc 1.0.8") == ("airc", "1.0.8")
    assert ac.parse_update_command("UPDATE airc") == ("airc", None)


def test_fr5532_prefixed_update_is_not_shell():
    core = _core(update_scheduler=_sched)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=8ddfdad8 UPDATE airc"
    )
    assert hr is not None
    assert hr.action == "update"
    text = hr.reply or ""
    assert "UPDATE accepted" in text
    assert "id=8ddfdad8" in text
    assert "DONE id=8ddfdad8 exit=0" in text
    assert "CommandNotFound" not in text


def test_fr5532_bare_update_still_has_id_and_done():
    core = _core(update_scheduler=_sched)
    hr = core.handle_raw(":bob-marchhare!u@h PRIVMSG marchhare_console :UPDATE airc")
    assert hr and hr.action == "update"
    text = hr.reply or ""
    assert "UPDATE accepted" in text
    assert "DONE id=" in text
    assert "exit=0" in text


def test_fr5532_failed_schedule_done_exit_1():
    def bad(product, version=None, **kwargs):
        return ac.UpdateScheduleResult(
            ok=False, status="skipped-pending", product=product, version=version
        )

    core = _core(update_scheduler=bad)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=aabbccdd UPDATE airc"
    )
    assert hr and hr.action == "update"
    assert "DONE id=aabbccdd exit=1" in (hr.reply or "")
    assert "skipped-pending" in (hr.reply or "")

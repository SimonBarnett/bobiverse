"""FR #5584: UPDATE result=current is success (DONE exit=0), not exit=1."""
from __future__ import annotations

import subprocess
from pathlib import Path

import airc_console as ac
from airc_auth_helpers import ops_auth


def test_fr5584_reply_line_current_exit_0():
    r = ac.UpdateScheduleResult(
        ok=True,
        status="current",
        detail="self-update: check result=current local=1.0.7 latest=1.0.7",
        product="airc",
        job_id="1af44e86",
    )
    text = r.reply_line()
    assert "UPDATE current" in text
    assert "UPDATE accepted" not in text
    assert "DONE id=1af44e86 exit=0" in text
    assert "exit=1" not in text


def test_fr5584_schedule_maps_current_to_ok(tmp_path, monkeypatch):
    upd = tmp_path / "Update-BobiverseService.ps1"
    upd.write_text("# stub updater\n", encoding="utf-8")
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("1.0.7\n", encoding="utf-8")

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="INFO self-update: check result=current local=1.0.7 latest=1.0.7\n",
            stderr="",
        )

    monkeypatch.setattr(ac.subprocess, "run", fake_run)
    res = ac.schedule_fleet_update(
        "airc",
        version=None,
        install_root=str(root),
        updater_script=str(upd),
        dry_run=True,
        no_spawn=True,
    )
    assert res.status == "current"
    assert res.ok is True
    text = res.reply_line()
    assert "UPDATE current" in text
    assert "DONE id=" in text and "exit=0" in text
    assert "exit=1" not in text


def test_fr5584_console_update_current_done_exit_0():
    def sched(product, version=None, **kwargs):
        return ac.UpdateScheduleResult(
            ok=True,
            status="current",
            detail="INFO self-update: check result=current local=1.0.7 latest=1.0.7",
            product=product,
            version=version,
        )

    auth = ops_auth("bob-marchhare", channel="#marchhare")
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=auth,
        nick="marchhare_console",
        update_scheduler=sched,
    )
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=1af44e86 UPDATE airc"
    )
    assert hr and hr.action == "update"
    text = hr.reply or ""
    assert "UPDATE current" in text
    assert "DONE id=1af44e86 exit=0" in text
    assert "exit=1" not in text

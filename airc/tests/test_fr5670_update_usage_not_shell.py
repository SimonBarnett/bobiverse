"""FR #5670: malformed UPDATE must not fall through to PowerShell; 404 exit!=0."""
from __future__ import annotations

import airc_console as ac
from airc_auth_helpers import ops_auth


def _core(**kw):
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(
        machine="marchhare", auth=auth, nick="marchhare_console", **kw
    )


def test_fr5670_parse_rejects_semicolon_tail():
    assert ac.parse_update_command("UPDATE airc 1.0.7;calc") is None
    assert ac.parse_update_command("id=11000001 UPDATE airc 1.0.7;calc") is None
    assert ac.update_usage_job_id("id=11000001 UPDATE airc 1.0.7;calc") == "11000001"
    assert ac.update_usage_job_id("UPDATE airc 1.0.7;calc") == ""
    assert ac.update_usage_job_id("UPDATE airc 1.0.7") is None
    assert ac.parse_update_command("UPDATE airc 1.0.7") == ("airc", "1.0.7")


def test_fr5670_malformed_update_is_usage_not_shell():
    calls: list = []

    def scheduler(product, version=None, **kwargs):
        calls.append((product, version))
        return ac.UpdateScheduleResult(True, "scheduled", product=product, version=version)

    core = _core(update_scheduler=scheduler)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console "
        ":id=11000001 UPDATE airc 1.0.7;calc"
    )
    assert hr is not None
    assert hr.action == "update"
    text = hr.reply or ""
    assert "code=usage" in text
    assert "UPDATE" in text
    assert "DONE id=11000001 exit=2" in text
    assert "CommandNotFound" not in text
    assert calls == []


def test_fr5670_update_bogus_product_usage():
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :UPDATE bogus"
    )
    assert hr and hr.action == "update"
    assert "code=usage" in (hr.reply or "")
    assert "DONE id=" in (hr.reply or "") and "exit=2" in (hr.reply or "")


def test_fr5670_update_extra_junk_usage():
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :UPDATE airc 1.0.7 extra junk"
    )
    assert hr and hr.action == "update"
    assert "code=usage" in (hr.reply or "")
    assert "exit=2" in (hr.reply or "")


def test_fr5670_update_force_flag_usage():
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :UPDATE airc -Force"
    )
    assert hr and hr.action == "update"
    assert "code=usage" in (hr.reply or "")
    assert "exit=2" in (hr.reply or "")


def test_fr5670_happy_update_still_schedules():
    calls: list = []

    def scheduler(product, version=None, **kwargs):
        calls.append((product, version))
        return ac.UpdateScheduleResult(
            True, "scheduled", product=product, version=version, job_id="aabbccdd"
        )

    core = _core(update_scheduler=scheduler)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=aabbccdd UPDATE airc 1.2.3"
    )
    assert hr and hr.action == "update"
    assert calls == [("airc", "1.2.3")]
    assert "exit=2" not in (hr.reply or "")
    assert "code=usage" not in (hr.reply or "")


def test_fr5670_release_lookup_failed_exit_nonzero(tmp_path, monkeypatch):
    # Updater may print release-lookup-failed and still exit 0 --- must be fail-closed.
    import subprocess

    upd = tmp_path / "Update-BobiverseService.ps1"
    upd.write_text("# stub updater\n", encoding="utf-8")
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("1.0.7\n", encoding="utf-8")

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="INFO self-update: check result=release-lookup-failed kind=http-404\n",
            stderr="",
        )

    monkeypatch.setattr(ac.subprocess, "run", fake_run)
    r = ac.schedule_fleet_update(
        "airc",
        version="99.99.99",
        install_root=str(root),
        updater_script=str(upd),
        dry_run=True,
        no_spawn=True,
    )
    assert r.status == "release-lookup-failed"
    assert r.ok is False
    assert "exit=0" not in r.reply_line()
    assert "exit=1" in r.reply_line()


def test_fr5670_skills_mention():
    from repo_layout import ROOT

    blob = (ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    ) + (ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "5670" in blob

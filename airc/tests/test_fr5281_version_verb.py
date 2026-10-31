"""FR #5281: VERSION console verb (airc install version, STATUS-like framing)."""
from __future__ import annotations

from unittest.mock import MagicMock

import airc_console as ac
from airc_auth_helpers import ops_auth
import airc_jobs as jobs


def test_fr5281_parse_version_verb():
    assert jobs.parse_job_verb("VERSION") == ("VERSION", {})
    assert jobs.parse_job_verb("id=c25bd00e VERSION") == ("VERSION", {"id": "c25bd00e"})
    assert jobs.verb_level("VERSION") == "read"


def test_fr5281_version_out_then_done(tmp_path):
    (tmp_path / "airc").mkdir()
    (tmp_path / "airc" / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    proto = jobs.JobProtocol(
        jobs.JobStore(tmp_path / "home"),
        ai_root=tmp_path,
        machine="tm",
        airc_running=True,
    )
    lines = proto.handle("bob-tm", "VERSION", {"id": "c25bd00e"})
    assert lines[0].startswith("out id=c25bd00e seq=1 VERSION machine=tm airc_ver=1.2.3")
    assert lines[-1] == "DONE id=c25bd00e exit=0"
    blob = "\n".join(lines).lower()
    assert "password" not in blob and "secret" not in blob


def test_fr5281_version_missing_file_is_dash(tmp_path):
    proto = jobs.JobProtocol(
        jobs.JobStore(tmp_path / "home"),
        ai_root=tmp_path,
        machine="box",
    )
    lines = proto.handle("bob-box", "VERSION", {"id": "aabbccdd"})
    assert "airc_ver=-" in lines[0]
    assert lines[-1].endswith("exit=0")


def test_fr5281_unauthorized_not_op():
    auth = ops_auth("op")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=MagicMock(),
    )
    hr = core.handle_raw(":evil!u@h PRIVMSG tm_console :VERSION")
    assert hr is not None and hr.action == "deny"
    assert "not-op" in (hr.reply or "").lower()


def test_fr5281_shell_off_and_jobs_off_allow_version():
    job = MagicMock()
    auth = ops_auth("op")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=job,
        capabilities=ac.ConsoleCapabilities(shell_mode="off", jobs="off"),
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=deadbeef VERSION")
    assert hr is not None and hr.action == "job"
    assert job.handle_async.call_args[0][1] == "VERSION"

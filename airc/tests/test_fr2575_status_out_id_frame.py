"""FR #2575: STATUS body framed as out id= seq= so Invoke-AircRemote StdOut fills."""
from __future__ import annotations

import airc_console as ac
import airc_jobs as jobs


def _versions(tmp_path):
    for name, ver in (("bob", "1.0.0"), ("airc", "1.0.0"), ("jeeves", "1.0.0")):
        d = tmp_path / name
        d.mkdir()
        (d / "VERSION").write_text(f"{ver}\n", encoding="utf-8")


def test_status_with_caller_id_frames_out_then_done(tmp_path):
    _versions(tmp_path)
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store, ai_root=tmp_path, machine="tm", airc_running=True)
    lines = proto.handle("bob-tm", "STATUS", {"id": "c25bd00e"})
    assert lines[0] == (
        "out id=c25bd00e seq=1 STATUS machine=tm airc=Running "
        "bob=1.0.0 airc_ver=1.0.0 jeeves=1.0.0"
    )
    assert lines[-1] == "DONE id=c25bd00e exit=0"
    assert len(lines) == 2


def test_status_without_caller_id_still_frames_out(tmp_path):
    """Minted id still uses out framing so ReplyFile StdOut contract is uniform."""
    _versions(tmp_path)
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store, ai_root=tmp_path, machine="tm", airc_running=True)
    lines = proto.handle("bob-tm", "STATUS", {})
    assert lines[0].startswith("out id=") and " seq=1 STATUS machine=tm" in lines[0]
    assert lines[-1].startswith("DONE id=") and lines[-1].endswith("exit=0")
    jid = lines[-1].split("id=")[1].split()[0]
    assert len(jid) == 8
    assert f"out id={jid} seq=1" in lines[0]


def test_handle_raw_id_status_emits_out_for_stdout(tmp_path):
    _versions(tmp_path)
    replies: list[str] = []
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(
        store,
        on_reply=lambda n, line: replies.append(line),
        ai_root=tmp_path,
        machine="tm",
        airc_running=True,
    )
    auth = ac.AuthPolicy(operators={"bob-tm"}, machine="tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=proto,
    )
    hr = core.handle_raw(":bob-tm!u@h PRIVMSG tm_console :id=aabbccdd STATUS")
    assert hr is not None and hr.action == "job"
    assert any(r.startswith("out id=aabbccdd seq=1 STATUS machine=tm") for r in replies)
    assert any(r == "DONE id=aabbccdd exit=0" for r in replies)


def test_format_status_lines_body_unchanged():
    """Raw STATUS body helper stays unframed; framing is JobProtocol's job."""
    lines = jobs.format_status_lines(
        airc_running=True,
        versions={"bob": "1", "airc": "2", "jeeves": "3"},
        machine="x",
    )
    assert lines[0].startswith("STATUS machine=x")
    assert not lines[0].startswith("out ")

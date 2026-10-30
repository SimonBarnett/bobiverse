"""FR #5211: bounded shell capture, resilient DONE, and Query cancellation."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time

import pytest

import airc_console as ac
import airc_jobs as jobs
from airc_auth_helpers import ops_auth


@pytest.mark.parametrize(
    "data,expected",
    [
        ("hello Ω".encode("utf-16"), "hello Ω"),
        ("hello Ω".encode("utf-16-le"), "hello Ω"),
        ("hello Ω".encode("utf-16-be"), "hello Ω"),
        (b"\xef\xbb\xbfhello", "hello"),
        (b"hello \xff\xfe", "hello \ufffd\ufffd"),
    ],
)
def test_capture_decodes_windows_output(data, expected):
    text, clipped = ac._clip_bytes(data)
    assert text == expected
    assert not clipped
    assert "\x00" not in text


def test_capture_snapshot_does_not_move_inherited_writer():
    with tempfile.NamedTemporaryFile() as writer:
        writer.write(b"first")
        writer.flush()
        position = writer.tell()
        assert ac._read_shell_capture(writer.name) == b"first"
        assert writer.tell() == position
        writer.write(b"-second")
        writer.flush()
        assert ac._read_shell_capture(writer.name) == b"first-second"


def test_capture_snapshot_is_bounded():
    with tempfile.NamedTemporaryFile() as writer:
        writer.write(b"x" * (ac.SHELL_OUTPUT_MAX_BYTES + 100))
        writer.flush()
        data = ac._read_shell_capture(writer.name)
    assert len(data) == ac.SHELL_OUTPUT_MAX_BYTES + 1
    assert ac._clip_bytes(data)[1]


def test_timeout_with_descendant_holding_output(monkeypatch):
    script = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'],"
        "stdout=sys.stdout,stderr=sys.stderr); "
        "print('partial',flush=True); time.sleep(20)"
    )
    monkeypatch.setattr(ac, "build_shell_argv", lambda req: [sys.executable, "-c", script])
    start = time.monotonic()
    outcome = ac.run_shell_request(ac.ShellRequest("ps", "ignored"), timeout_s=0.5)
    assert time.monotonic() - start < 6
    assert outcome.exit_code == 124
    assert "partial" in outcome.stdout
    assert "timeout" in outcome.stderr
    assert ac.format_shell_replies(outcome)[-1].endswith("exit=124")


def test_exited_parent_does_not_wait_for_descendant_eof(monkeypatch, tmp_path):
    pid_file = tmp_path / "child.pid"
    script = (
        "import subprocess,sys,pathlib; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'],"
        "stdout=sys.stdout,stderr=sys.stderr); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
        "print('parent-exited',flush=True)"
    )
    monkeypatch.setattr(ac, "build_shell_argv", lambda req: [sys.executable, "-c", script])
    try:
        start = time.monotonic()
        outcome = ac.run_shell_request(ac.ShellRequest("ps", "ignored"), timeout_s=0.5)
        assert time.monotonic() - start < 3
        assert outcome.exit_code == 0
        assert "parent-exited" in outcome.stdout
    finally:
        if pid_file.exists():
            pid = int(pid_file.read_text())
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
                )
            else:
                try:
                    os.kill(pid, 9)
                except ProcessLookupError:
                    pass


def test_non_utf8_capture_and_clipping(monkeypatch):
    script = "import sys; sys.stdout.buffer.write(b'\\xff'*65000); sys.stderr.buffer.write(b'\\x80')"
    monkeypatch.setattr(ac, "build_shell_argv", lambda req: [sys.executable, "-c", script])
    outcome = ac.run_shell_request(ac.ShellRequest("ps", "ignored"), timeout_s=5)
    assert outcome.exit_code == 0
    assert outcome.stdout.endswith("[clipped stdout]")
    assert outcome.stderr == "\ufffd"
    assert ac.format_shell_replies(outcome)[-1].endswith("exit=0")


@pytest.mark.parametrize("fault", ["encode", "format"])
def test_output_fault_still_finishes_and_runs_next_job(monkeypatch, fault):
    replies = []
    started = threading.Event()
    release = threading.Event()

    def fake_run(req, **kwargs):
        if req.job_id == "11111111":
            started.set()
            assert release.wait(3)
            text = "\udcff" if fault == "format" else "unencodable"
        else:
            text = "next"
        return ac.ShellOutcome(req.job_id, 0, text, "")

    def reply(nick, line):
        if "unencodable" in line:
            raise UnicodeEncodeError("ascii", "Ω", 0, 1, "test")
        replies.append(line)

    monkeypatch.setattr(ac, "run_shell_request", fake_run)
    runner = ac.ShellJobRunner(on_reply=reply)
    runner.start("op", "id=11111111 first")
    assert started.wait(3)
    runner.start("op", "id=22222222 second")
    thread = runner._threads["op"]
    release.set()
    thread.join(3)
    assert not thread.is_alive()
    assert any(line.startswith("DONE id=11111111 ") for line in replies)
    assert "DONE id=22222222 exit=0" in replies
    assert runner.open_job_ids() == []


def test_cancel_clears_active_and_pending_while_status_stays_responsive(monkeypatch, tmp_path):
    replies = []
    started = threading.Event()
    real_run = ac.run_shell_request

    def run(req, **kwargs):
        started.set()
        return real_run(req, **kwargs)

    monkeypatch.setattr(ac, "run_shell_request", run)
    monkeypatch.setattr(
        ac, "build_shell_argv",
        lambda req: [sys.executable, "-c", "import time; time.sleep(20)"],
    )
    runner = ac.ShellJobRunner(on_reply=lambda n, line: replies.append(line))
    proto = jobs.JobProtocol(
        jobs.JobStore(tmp_path / "home"), ai_root=tmp_path, machine="tm",
        on_reply=lambda n, line: replies.append(line),
    )
    core = ac.AircConsoleCore(
        auth=ops_auth("op", "other"), nick="tm_console", shell_runner=runner,
        job_protocol=proto,
    )
    runner.start("op", "id=11111111 first")
    assert started.wait(3)
    runner.start("op", "id=22222222 queued")
    queued = runner._pending["op"][0]
    assert not runner.cancel("other", "11111111")
    core.handle_raw(":op!u@h PRIVMSG tm_console :id=33333333 STATUS")
    assert "DONE id=33333333 exit=0" in replies
    thread = runner._threads["op"]
    core.handle_raw(":op!u@h PRIVMSG tm_console :CANCEL id=11111111")
    thread.join(6)
    assert not thread.is_alive()
    assert queued.done.is_set()
    assert "DONE id=11111111 exit=130" in replies
    assert "DONE id=22222222 exit=130" in replies
    assert replies.count("DONE id=11111111 exit=130") == 1
    assert runner.open_job_ids() == []
    monkeypatch.setattr(
        ac, "build_shell_argv", lambda req: [sys.executable, "-c", "print('recovered')"],
    )
    runner.wait = True
    runner.start("op", "id=44444444 recovered")
    assert "DONE id=44444444 exit=0" in replies


def test_cancel_preserves_exec_authorization(monkeypatch, tmp_path):
    runner = ac.ShellJobRunner()
    calls = []
    monkeypatch.setattr(runner, "cancel", lambda *args: calls.append(args))
    replies = []
    proto = jobs.JobProtocol(
        jobs.JobStore(tmp_path / "home"),
        verb_auth=jobs.VerbAuthPolicy(exec_nicks={"other"}),
        on_reply=lambda n, line: replies.append(line),
    )
    core = ac.AircConsoleCore(
        auth=ops_auth("op"), nick="tm_console", shell_runner=runner, job_protocol=proto,
    )
    core.handle_raw(":op!u@h PRIVMSG tm_console :CANCEL id=11111111")
    assert not calls
    assert any("code=denied" in line for line in replies)

"""FR #5211: bounded capture, malformed output, cancellation, and queue recovery."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from types import SimpleNamespace

import pytest

import airc_console as ac
import airc_console_service as svc
from airc_auth_helpers import ops_auth
from airc_jobs import JobProtocol, JobStore, VerbAuthPolicy


def _python_shell(monkeypatch):
    monkeypatch.setattr(ac, "build_shell_argv", lambda req: [sys.executable, "-c", req.body])


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-be", "utf-8"])
def test_encoded_output_finishes_and_has_no_irc_nul(monkeypatch, encoding):
    _python_shell(monkeypatch)
    data = "example=\u03b1\r\n".encode(encoding)
    if encoding == "utf-16-be":
        data = b"\xfe\xff" + data
    req = ac.ShellRequest("ps", f"import sys; sys.stdout.buffer.write({data!r})", "aaaa1111")
    outcome = ac.run_shell_request(req, timeout_s=2)
    assert outcome.stdout == "example=\u03b1\r\n"
    lines = ac.format_shell_replies(outcome)
    assert lines[-1] == "DONE id=aaaa1111 exit=0"
    assert all("\x00" not in line for line in lines)


def test_binary_and_invalid_utf8_still_finish(monkeypatch):
    _python_shell(monkeypatch)
    outcome = ac.run_shell_request(
        ac.ShellRequest("ps", "import sys; sys.stdout.buffer.write(b'\\xff\\x00bad\\x00')"),
        timeout_s=2,
    )
    lines = ac.format_shell_replies(outcome)
    assert lines[-1].endswith("exit=0")
    assert all("\x00" not in line for line in lines)


def test_inherited_capture_handle_does_not_hold_timeout(monkeypatch):
    _python_shell(monkeypatch)
    # A descendant holds stdout open after the direct child exits. No pipe EOF
    # is needed, and no broad process-name kill is involved.
    script = (
        "import subprocess, sys; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)']); "
        "print('partial', flush=True)"
    )
    start = time.monotonic()
    result = ac.run_shell_request(ac.ShellRequest("ps", script), timeout_s=0.2)
    assert time.monotonic() - start < 1.5
    assert result.exit_code == 0
    assert "partial" in result.stdout


def test_multibyte_output_stays_within_irc_byte_budget():
    outcome = ac.ShellOutcome("aaaa1111", 0, "\u03b1\u4e16\U0001f600" * 200, "")
    lines = ac.format_shell_replies(outcome)
    assert all(len(line.encode("utf-8")) <= ac.IRC_SAFE_PAYLOAD for line in lines)
    assert "".join(line.split(" ", 3)[-1] for line in lines[:-1]) == outcome.stdout
    assert lines[-1] == "DONE id=aaaa1111 exit=0"


def test_capture_snapshot_does_not_reposition_inherited_writer():
    with tempfile.NamedTemporaryFile() as capture:
        capture.write(b"first")
        capture.flush()
        assert ac._read_shell_capture(capture.name) == b"first"
        capture.write(b"second")
        capture.flush()
        assert ac._read_shell_capture(capture.name) == b"firstsecond"


def test_shutdown_between_dequeue_and_execution_cannot_launch_shell(monkeypatch):
    seen = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line))
    dequeued = threading.Event()
    proceed = threading.Event()
    run_one = runner._run_one

    def pause(key, item):
        dequeued.set()
        assert proceed.wait(2)
        run_one(key, item)

    monkeypatch.setattr(runner, "_run_one", pause)
    monkeypatch.setattr(
        ac.subprocess, "Popen",
        lambda *args, **kw: pytest.fail("abandoned shell must not launch"),
    )
    runner.start("op", "id=aaaa1111 echo never")
    assert dequeued.wait(2)
    with runner._lock:
        item = runner._inflight_cmd["op"]
        worker = runner._threads["op"]
    runner.abandon_open_jobs()
    proceed.set()
    worker.join(2)
    assert item.cancelled.is_set()
    assert not worker.is_alive()
    assert seen == []  # Shutdown owns the terminal reply after abandonment.


def test_shutdown_owns_single_done_even_when_worker_finishes_during_flush(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(["--machine", "tm", "--home", str(tmp_path)])
    service = svc.AircConsoleService(args)
    service.sock = object()
    sent = []
    service.send_privmsg = lambda nick, text, **kw: sent.append(text)
    started = threading.Event()

    def run(req, **kw):
        started.set()
        assert req.cancel_event.wait(2)
        return ac.ShellOutcome(req.job_id, 130, "", "cancelled")

    monkeypatch.setattr(ac, "run_shell_request", run)
    service.shell_runner.start("op", "id=aaaa1111 echo never")
    assert started.wait(2)
    with service.shell_runner._lock:
        worker = service.shell_runner._threads["op"]
    abandon = service.shell_runner.abandon_open_jobs

    def abandon_and_finish():
        ids = abandon()
        worker.join(2)
        assert not worker.is_alive()
        return ids

    monkeypatch.setattr(service.shell_runner, "abandon_open_jobs", abandon_and_finish)
    service.flush_stop_dones()
    assert [line for line in sent if line.startswith("DONE")] == ["DONE id=aaaa1111 exit=1"]
    assert len([line for line in sent if line.startswith("err")]) == 1


def test_windows_cleanup_is_pid_scoped_and_bounded(monkeypatch):
    calls = []
    monkeypatch.setattr(ac, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(ac.subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    proc = SimpleNamespace(
        pid=12345, kill=lambda: calls.append("kill"),
        wait=lambda **kw: calls.append(("wait", kw)),
    )
    ac._stop_shell_process(proc)
    args, kwargs = calls[0]
    assert args == ["taskkill.exe", "/PID", "12345", "/T", "/F"]
    assert kwargs["timeout"] == 5
    assert calls[-1] == ("wait", {"timeout": 5})


def test_generated_shell_id_is_stable_and_cancellable(monkeypatch):
    started = threading.Event()
    seen = []

    def run(req, **kw):
        started.set()
        assert req.cancel_event.wait(2)
        return ac.ShellOutcome(req.job_id, 130, "", "cancelled")

    monkeypatch.setattr(ac, "run_shell_request", run)
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line))
    runner.start("op", "echo generated-id")
    assert started.wait(2)
    ids = runner.open_job_ids()
    assert ids == runner.open_job_ids()
    nick, jid = ids[0]
    with runner._lock:
        worker = runner._threads[nick]
    assert runner.cancel(nick, jid)
    worker.join(2)
    assert f"DONE id={jid} exit=130" in seen
    assert runner.open_job_ids() == []


def test_timeout_returns_partial_output_and_queue_advances(monkeypatch):
    _python_shell(monkeypatch)
    seen = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line), timeout_s=0.2)
    runner.start("op", "id=aaaa1111 import time; print('partial', flush=True); time.sleep(10)")
    runner.start("op", "id=bbbb2222 print('next')")
    deadline = time.monotonic() + 3
    while "DONE id=bbbb2222 exit=0" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    assert "DONE id=aaaa1111 exit=124" in seen
    assert "DONE id=bbbb2222 exit=0" in seen
    assert any("partial" in line for line in seen)


def test_cancel_active_and_pending_shells_then_status_and_new_command(monkeypatch, tmp_path):
    _python_shell(monkeypatch)
    seen = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line), timeout_s=10)
    jobs = JobProtocol(JobStore(tmp_path), on_reply=lambda n, line: seen.append(line))
    core = ac.AircConsoleCore(
        machine="tm", auth=ops_auth("op", "other"), shell_runner=runner, job_protocol=jobs,
    )
    core.handle_raw(":op!u@h PRIVMSG tm_console :id=aaaa1111 import time; time.sleep(10)")
    core.handle_raw(":op!u@h PRIVMSG tm_console :id=bbbb2222 print('must-not-run')")
    deadline = time.monotonic() + 2
    while "op" not in runner._inflight_cmd and time.monotonic() < deadline:
        time.sleep(0.01)
    core.handle_raw(":op!u@h PRIVMSG tm_console :id=cccc3333 STATUS")
    assert "DONE id=cccc3333 exit=0" in seen
    assert "DONE id=aaaa1111 exit=0" not in seen
    assert not runner.cancel("other", "aaaa1111")
    core.handle_raw(":op!u@h PRIVMSG tm_console :CANCEL id=bbbb2222")
    core.handle_raw(":op!u@h PRIVMSG tm_console :CANCEL id=aaaa1111")
    core.handle_raw(":op!u@h PRIVMSG tm_console :id=dddd4444 print('recovered')")
    deadline = time.monotonic() + 3
    while "DONE id=dddd4444 exit=0" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    for jid in ("aaaa1111", "bbbb2222"):
        assert seen.count(f"DONE id={jid} exit=130") == 1
    assert "DONE id=cccc3333 exit=0" in seen
    assert "DONE id=dddd4444 exit=0" in seen
    assert not any("must-not-run" in line for line in seen)
    assert runner.open_job_ids() == []


def test_cancel_preserves_job_authorization(monkeypatch, tmp_path):
    runner = ac.ShellJobRunner()
    called = []
    monkeypatch.setattr(runner, "cancel", lambda *args: called.append(args))
    jobs = JobProtocol(JobStore(tmp_path), verb_auth=VerbAuthPolicy(exec_nicks={"other"}))
    core = ac.AircConsoleCore(
        machine="tm", auth=ops_auth("op"), shell_runner=runner, job_protocol=jobs,
    )
    core.handle_raw(":op!u@h PRIVMSG tm_console :CANCEL id=aaaa1111")
    assert called == []
    core.handle_raw(":stranger!u@h PRIVMSG tm_console :CANCEL id=aaaa1111")
    assert called == []


@pytest.mark.parametrize("error", [UnicodeEncodeError("ascii", "\u03b1", 0, 1, "bad"), ValueError("bad")])
def test_reply_failure_cannot_lose_done_or_wedge_next_job(monkeypatch, error):
    seen = []

    def reply(_nick, line):
        if line.startswith("out id=aaaa1111"):
            raise error
        seen.append(line)

    monkeypatch.setattr(
        ac, "run_shell_request",
        lambda req, **kw: ac.ShellOutcome(req.job_id, 0, "test\n", ""),
    )
    runner = ac.ShellJobRunner(on_reply=reply, wait=True)
    runner.start("op", "id=aaaa1111 echo first")
    runner.start("op", "id=bbbb2222 echo second")
    assert any(line.startswith("DONE id=aaaa1111") for line in seen)
    assert "DONE id=bbbb2222 exit=0" in seen


def test_formatter_fault_emits_done_and_drains_next_job(monkeypatch):
    seen = []
    monkeypatch.setattr(
        ac, "run_shell_request",
        lambda req, **kw: ac.ShellOutcome(req.job_id, 0, "test\n", ""),
    )
    original = ac.format_shell_replies_ex

    def format_reply(outcome, **kw):
        if outcome.job_id == "aaaa1111":
            raise UnicodeError("formatting failed")
        return original(outcome, **kw)

    monkeypatch.setattr(ac, "format_shell_replies_ex", format_reply)
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line), wait=True)
    runner.start("op", "id=aaaa1111 echo first")
    runner.start("op", "id=bbbb2222 echo second")
    assert "DONE id=aaaa1111 exit=1" in seen
    assert "DONE id=bbbb2222 exit=0" in seen

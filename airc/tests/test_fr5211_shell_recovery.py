"""FR #5211: bounded capture, malformed output, cancellation, and queue recovery."""
from __future__ import annotations

import sys
import time

import pytest

import airc_console as ac
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

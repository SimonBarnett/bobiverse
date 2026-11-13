"""FR #7119: isolate Cmd trees, hard timeout wording, cancel while busy, STATUS shell_busy."""
from __future__ import annotations

import sys
import time

import airc_console as ac
from airc_auth_helpers import ops_auth
from airc_jobs import JobProtocol, JobStore, format_status_lines


def _python_shell(monkeypatch):
    monkeypatch.setattr(ac, "build_shell_argv", lambda req: [sys.executable, "-c", req.body])


def test_timeout_stderr_says_killed_timeout(monkeypatch):
    _python_shell(monkeypatch)
    outcome = ac.run_shell_request(
        ac.ShellRequest("ps", "import time; time.sleep(10)"),
        timeout_s=0.2,
    )
    assert outcome.exit_code == 124
    assert "killed: timeout" in outcome.stderr
    assert "killed: no-output" in outcome.stderr


def test_cancel_mixed_case_job_id_kills_busy_shell(monkeypatch):
    _python_shell(monkeypatch)
    seen = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line), timeout_s=10)
    runner.start("op", "id=aaaa1111 import time; time.sleep(10)")
    deadline = time.monotonic() + 2
    while "op" not in runner._inflight_cmd and time.monotonic() < deadline:
        time.sleep(0.01)
    assert runner.cancel("op", "AAAA1111")
    deadline = time.monotonic() + 3
    while "DONE id=aaaa1111 exit=130" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    assert "DONE id=aaaa1111 exit=130" in seen
    assert runner.open_job_ids() == []


def test_status_includes_shell_busy_when_cmd_inflight(monkeypatch, tmp_path):
    _python_shell(monkeypatch)
    seen = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line), timeout_s=10)
    jobs = JobProtocol(JobStore(tmp_path), on_reply=lambda n, line: seen.append(line), machine="tm")
    core = ac.AircConsoleCore(
        machine="tm", auth=ops_auth("op", "other"), shell_runner=runner, job_protocol=jobs,
    )
    core.handle_raw(":op!u@h PRIVMSG tm_console :id=aaaa1111 import time; time.sleep(10)")
    deadline = time.monotonic() + 2
    while "op" not in runner._inflight_cmd and time.monotonic() < deadline:
        time.sleep(0.01)
    core.handle_raw(":op!u@h PRIVMSG tm_console :id=cccc3333 STATUS")
    assert any(
        "STATUS machine=tm" in line and "shell_busy=1" in line and "shell_job=aaaa1111" in line
        for line in seen
    )
    runner.cancel("op", "aaaa1111")


def test_format_status_lines_idle_unchanged():
    lines = format_status_lines(
        airc_running=True,
        versions={"bob": "1", "airc": "2", "jeeves": "3"},
        machine="x",
    )
    assert lines[0] == "STATUS machine=x airc=Running bob=1 airc_ver=2 jeeves=3"


def test_cancel_kills_process_tree_promptly(monkeypatch):
    _python_shell(monkeypatch)
    seen = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: seen.append(line), timeout_s=30)
    t0 = time.monotonic()
    runner.start("op", "id=bbbb2222 import time; time.sleep(30)")
    deadline = time.monotonic() + 2
    while "op" not in runner._inflight_cmd and time.monotonic() < deadline:
        time.sleep(0.01)
    inflight = runner._inflight_cmd.get("op")
    wait_proc = time.monotonic() + 2
    while inflight is not None and inflight.runtime.get("proc") is None and time.monotonic() < wait_proc:
        time.sleep(0.01)
    assert runner.cancel("op", "bbbb2222")
    deadline = time.monotonic() + 5
    while "DONE id=bbbb2222 exit=130" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    assert "DONE id=bbbb2222 exit=130" in seen
    assert time.monotonic() - t0 < 4

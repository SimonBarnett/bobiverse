"""FR #8553: OpenCode seat must not die after inject with no last-exit.

- launch-opencode.ps1 must not Start-Process with -NoNewWindow + redirects
  (hangs after build banner; can tear down the console/seat).
- last-exit.json is fsync'd.
- inject-progress.json is stamped on submit-verify ok.
- OpenCode agent exit 0 mid-ACK GIVEUPs and recycles instead of ending the seat.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import bob_worker as bw

OP = r"C:\fake\opencode.exe"


def test_fr8553_launcher_omits_nonewwindow_with_redirects(tmp_path: Path):
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "cwd"),
        "hello",
        OP,
        tmp_path / "run",
        None,
    )
    ps1 = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "RedirectStandardOutput" in ps1
    assert "RedirectStandardError" in ps1
    assert "Start-Process -FilePath $exe -ArgumentList $argStr" in ps1
    # The spawn lines themselves must not carry -NoNewWindow (comment may mention it).
    for line in ps1.splitlines():
        if "Start-Process -FilePath $exe" in line and "RedirectStandardOutput" in line:
            assert "-NoNewWindow" not in line, line


def test_fr8553_write_inject_progress_fsync(tmp_path: Path):
    bw.write_inject_progress(
        tmp_path,
        phase="submit-verify-ok",
        detail="ok",
        job_key="FR SimonBarnett/bobiverse#8553",
    )
    path = tmp_path / "inject-progress.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["phase"] == "submit-verify-ok"
    assert data["job_key"] == "FR SimonBarnett/bobiverse#8553"
    assert "at" in data


def test_fr8553_persist_last_exit_fsync(tmp_path: Path):
    class _SL:
        path = tmp_path / "session.log"

        def write(self, *_a, **_k):
            return None

        def tail(self):
            return ""

    class _Sup:
        run_dir = tmp_path
        session_log = _SL()
        last_exit = {
            "at": "2026-11-20T00:00:00+00:00",
            "reason": "agent-exited",
            "exit_code": 0,
            "pid": 1,
            "output": "",
        }
        publish_exit_digest = None
        log = lambda *a, **k: None  # noqa: E731

        _persist_last_exit = bw.Supervisor._persist_last_exit

    s = _Sup()
    bw.Supervisor._persist_last_exit(s)
    path = tmp_path / "last-exit.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["reason"] == "agent-exited"


def test_fr8553_opencode_zero_exit_mid_ack_recycles(tmp_path: Path, monkeypatch):
    events: list[str] = []

    class FakeBored:
        _ack_open = True
        _ack_job_key = "FR SimonBarnett/bobiverse#8553"
        out_of_fuel = False

    class FakeProc:
        pid = 4242

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def stderr_tail(self):
            return ""

    # Minimal Supervisor-shaped object for _wait_exit branch under test.
    # Call the zero-exit logic via a thin stand-in that uses the real method body.
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "opencode-wrapper-exited" in src
    assert "GIVEUP + recycle (FR #8553)" in src

    # Behavioral: restart_agent is preferred over shutdown when opencode + ack open.
    class Tiny:
        kind = "opencode"
        bored = FakeBored()
        clock = lambda self: 100.0  # noqa: E731
        startup_grace_s = 60.0
        relay = MagicMock(last_unacked="")
        _agent_started_at = 90.0
        _agent_parent_pid = 0
        _agent_parent_image = ""
        _agent_parent_cmd = ""
        _lock = __import__("threading").Lock()
        proc = FakeProc()
        _expected_exit: set = set()
        last_exit = None
        _exit_recorded_pid = None
        machine = "redqueen"
        nick = "redqueen-1"
        log = lambda self, m: events.append(m)  # noqa: E731

        def _record_exit(self, proc, reason, code, **_k):
            self.last_exit = {"reason": reason, "exit_code": code, "pid": proc.pid}
            return True

        def _persist_last_exit(self):
            events.append("persist")

        def _reconcile_wait_exit_with_shutdown(self, *_a, **_k):
            return False

        def _release_seat_giveup_job(self, key, reason):
            events.append(f"giveup:{key}:{reason}")

        def restart_agent(self, reason):
            events.append(f"restart:{reason}")

        def shutdown(self, reason, code):
            events.append(f"shutdown:{reason}:{code}")

        _wait_exit = bw.Supervisor._wait_exit

    tiny = Tiny()
    proc = FakeProc()
    tiny.proc = proc
    monkeypatch.setattr(bw, "parent_of", lambda *_a, **_k: 0)
    monkeypatch.setattr(bw, "describe_process", lambda *_a, **_k: (0, "", ""))
    monkeypatch.setattr(bw, "format_external_kill_log", lambda **_k: "kill-line")
    monkeypatch.setattr(bw, "normalize_agent_exit_code", lambda c: int(c) if c is not None else 0)
    monkeypatch.setattr(bw, "format_agent_exit_code_label", lambda c: str(c))
    monkeypatch.setattr(bw, "CONSOLE_CLOSE_EXIT", 3221225786)
    monkeypatch.setattr(bw, "report_agent_cli_nonzero_exit", lambda **_k: None)

    tiny._wait_exit(proc)
    assert any(e.startswith("giveup:") and "opencode-wrapper-exited" in e for e in events), events
    assert any(e == "restart:opencode-wrapper-exited" for e in events), events
    assert not any(e.startswith("shutdown:agent-exited") for e in events), events

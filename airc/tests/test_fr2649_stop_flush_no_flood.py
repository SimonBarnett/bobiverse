"""FR #2649: SCM stop during Command must deliver DONE (no flood gap / no double flush).

Live MarchHare after #2644 (id c8ed3a28): Restart-Service mid-Command left
`out long-start` + `err session interrupted` but no DONE. Log showed
`session interrupted -> stop` then `console-out-send-err … 10038` then
`stop-flush-send-err send: no socket`.

Cause: stop flush drained err then slept FLOOD_S (0.35s) before DONE; SCM
invalidated the socket in that gap. `run()` finally then re-flushed with
sock already None.
"""
from __future__ import annotations

import airc_console_service as svc


def _svc(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    return svc.AircConsoleService(args)


class _RecordingSock:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False

    def sendall(self, data: bytes) -> None:  # noqa: ANN001
        if self.closed:
            raise OSError(10038, "An operation was attempted on something that is not a socket")
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


def test_fr2649_stop_flush_skips_flood_sleep(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.35)
    sleeps: list[float] = []

    def track_sleep(sec: float) -> None:
        sleeps.append(float(sec))
        # Simulate SCM killing the socket during a flood gap after err.
        if sec >= 0.3 and s.sock is not None:
            try:
                s.sock.close()
            except Exception:
                pass

    monkeypatch.setattr(svc.time, "sleep", track_sleep)
    sock = _RecordingSock()
    s.sock = sock
    s.note_shell_inflight("bob-tm", "c8ed3a28")

    s.prepare_stop(reason="session interrupted")
    joined = b"".join(sock.sent).decode("utf-8", errors="replace")
    assert "DONE id=c8ed3a28 exit=1" in joined
    assert "err id=c8ed3a28" in joined
    assert not any(x >= 0.3 for x in sleeps), f"flood sleep during stop flush: {sleeps}"
    assert s._stop_flushed is True


def test_fr2649_finally_does_not_reflush_after_prepare_stop(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    sock = _RecordingSock()
    s.sock = sock
    s.note_shell_inflight("bob-tm", "ed7fca46")
    s.prepare_stop(reason="session interrupted")
    assert s.sock is None
    assert s._stop_flushed is True
    logs: list[str] = []
    monkeypatch.setattr(svc, "info", lambda msg: logs.append(str(msg)))
    s.flush_stop_dones(reason="service-stop")
    assert not any("stop-flush-send-err" in m for m in logs)
    assert not any("send: no socket" in m for m in logs)


def test_fr2649_stop_flush_skip_when_sock_already_none(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    s.sock = None
    s.note_shell_inflight("bob-tm", "aabbccdd")
    logs: list[str] = []
    monkeypatch.setattr(svc, "info", lambda msg: logs.append(str(msg)))
    s.flush_stop_dones(reason="session interrupted")
    assert any("stop-flush-skip" in m for m in logs)
    assert not any("stop-flush-send-err" in m for m in logs)
    assert s._stop_flushed is True


def test_fr2649_read_loop_paths_call_prepare_stop():
    from pathlib import Path

    src = Path(svc.__file__).read_text(encoding="utf-8")
    assert 'prepare_stop(reason="probe interrupted")' in src
    assert 'prepare_stop(reason="reap interrupted")' in src
    assert 'prepare_stop(reason="keepalive interrupted")' in src
    assert 'prepare_stop(reason="recv interrupted")' in src
    assert 'prepare_stop(reason="session interrupted")' in src

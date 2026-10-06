"""FR #2640: service stop must emit in-flight/queued shell DONE before socket close.

Live MarchHare (id be90eb40): Stop-Service Airc mid-Command left ear with out/err
lines but no DONE; airc-console.log showed ``session interrupted -> stop`` then
``console-out-send-err … WinError 10038`` — stop-flush drained after the socket
was already invalid / closed, and the outbound queue died with the process.
"""
from __future__ import annotations

import threading

import airc_console_service as svc


def _svc(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    return svc.AircConsoleService(args)


class _CloseTrackingSock:
    """Records sends; raises WinError 10038 after close (live stop failure mode)."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False
        self.sends_after_close = 0

    def sendall(self, data: bytes) -> None:  # noqa: ANN001
        if self.closed:
            self.sends_after_close += 1
            raise OSError(10038, "An operation was attempted on something that is not a socket")
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


def test_fr2640_stop_flush_writes_done_before_socket_close(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    sock = _CloseTrackingSock()
    s.sock = sock
    s.note_shell_inflight("bob-tm", "be90eb40")

    s.prepare_stop(reason="session interrupted")
    joined = b"".join(sock.sent).decode("utf-8", errors="replace")
    assert "DONE id=be90eb40 exit=1" in joined
    assert sock.closed is True
    assert sock.sends_after_close == 0
    assert s.shell_inflight() == {}
    assert s.out_queue_size() == 0


def test_fr2640_stop_flush_includes_pending_queued_ids(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    sock = _CloseTrackingSock()
    s.sock = sock

    hold = threading.Event()
    release = threading.Event()

    def blocker() -> None:
        hold.set()
        release.wait(timeout=5)

    t = threading.Thread(target=blocker, name="airc-shell-bob-tm", daemon=True)
    with s.shell_runner._lock:
        s.shell_runner._threads["bob-tm"] = t
    t.start()
    assert hold.wait(timeout=2)
    try:
        s.note_shell_inflight("bob-tm", "11111111")
        s.shell_runner.start("bob-tm", "id=22222222 Write-Output pending-should-done")
        pending = s.shell_runner.open_job_ids()
        assert any(jid == "22222222" for _n, jid in pending)

        s.prepare_stop(reason="service-stop")
        joined = b"".join(sock.sent).decode("utf-8", errors="replace")
        assert "DONE id=11111111 exit=1" in joined
        assert "DONE id=22222222 exit=1" in joined
        assert sock.sends_after_close == 0
    finally:
        release.set()
        t.join(timeout=2)


def test_fr2640_late_console_out_during_stop_does_not_send_after_close(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    sock = _CloseTrackingSock()
    s.sock = sock
    s.note_shell_inflight("bob-tm", "aabbccdd")

    s.prepare_stop(reason="session interrupted")
    before = sock.sends_after_close
    s._on_console_out("bob-tm", "err id=aabbccdd seq=1 session interrupted")
    s._on_console_out("bob-tm", "out id=aabbccdd seq=2 late")
    assert sock.sends_after_close == before

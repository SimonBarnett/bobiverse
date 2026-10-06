"""FR #2612: long Command output must not stall after seq=1 when IRC drops/reconnects/stops.

Live MarchHare evidence (id cf38f565): only seq=1 reached airc-replies.jsonl; airc-console.log
showed ``probe interrupted -> stop`` then full process restart mid-emit. Wait timed out with no DONE.

Acceptance:
1. Outbound reply queue retains lines across ConnectionError / force_reconnect; drain after sock returns.
2. Graceful stop flushes DONE for in-flight shell job ids so Wait can finish.
3. Overlapping shell on the same Query is queued (FR #2632); only a full pending queue
   fail-closes with busy DONE so Wait never hangs without a DONE.
"""
from __future__ import annotations

import airc_console as ac
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

    def sendall(self, data: bytes) -> None:  # noqa: ANN001
        self.sent.append(data)


def test_fr2612_out_queue_survives_reconnect_then_drains(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    s.sock = None
    s._force_reconnect = False
    # Enqueue while down — must not raise; must keep lines.
    s._on_console_out("bob-tm", "out id=aabbccdd seq=1 LINE1")
    s._on_console_out("bob-tm", "out id=aabbccdd seq=2 LINE2")
    s._on_console_out("bob-tm", "DONE id=aabbccdd exit=0")
    assert s._force_reconnect is True
    assert s.out_queue_size() >= 3
    # Sock returns (reconnect): drain must deliver all three.
    sock = _RecordingSock()
    s.sock = sock
    s._force_reconnect = False
    n = s.drain_out_queue()
    assert n >= 3
    joined = b"".join(sock.sent).decode("utf-8", errors="replace")
    assert "out id=aabbccdd seq=1" in joined
    assert "out id=aabbccdd seq=2" in joined
    assert "DONE id=aabbccdd exit=0" in joined
    assert s.out_queue_size() == 0


def test_fr2612_stop_flush_emits_done_for_inflight(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    sock = _RecordingSock()
    s.sock = sock
    s.note_shell_inflight("bob-tm", "cf38f565")
    s.flush_stop_dones(reason="probe interrupted")
    joined = b"".join(sock.sent).decode("utf-8", errors="replace")
    assert "id=cf38f565" in joined
    assert "DONE id=cf38f565 exit=" in joined
    assert s.shell_inflight() == {}


def test_fr2612_overlapping_shell_queue_full_busy_done():
    """FR #2612/#2632: only a full pending queue fail-closes with busy DONE."""
    seen: list[str] = []

    def capture(nick: str, line: str) -> None:
        seen.append(line)

    runner = ac.ShellJobRunner(on_reply=capture, wait=False, pending_max=0)
    # Fake a live prior thread with pending_max=0 → any overlap is overflow.
    import threading

    hold = threading.Event()

    def blocker() -> None:
        hold.wait(timeout=2)

    t = threading.Thread(target=blocker, name="airc-shell-bob-tm", daemon=True)
    with runner._lock:
        runner._threads["bob-tm"] = t
    t.start()
    try:
        runner.start("bob-tm", "id=deadbeef Write-Output hi")
        assert any(x.startswith("err id=deadbeef") and "busy" in x.lower() for x in seen)
        assert any(x == "DONE id=deadbeef exit=1" for x in seen)
    finally:
        hold.set()
        t.join(timeout=2)


def test_fr2612_shell_runner_notes_inflight(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    s.sock = _RecordingSock()
    notes: list[tuple[str, str]] = []

    def on_reply(nick: str, line: str) -> None:
        s._on_console_out(nick, line)

    runner = ac.ShellJobRunner(
        on_reply=on_reply,
        wait=True,
        timeout_s=15,
        on_inflight=s.note_shell_inflight,
        on_idle=s.clear_shell_inflight,
    )
    # Instant command
    runner.start("bob-tm", "id=abcd1234 Write-Output one")
    # After wait=True join, inflight cleared
    assert "bob-tm" not in s.shell_inflight()

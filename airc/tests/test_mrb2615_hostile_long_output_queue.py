"""MRB #2615 hostile gates for FR #2612 outbound queue / stop DONE / busy overlap."""
from __future__ import annotations

from pathlib import Path

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
        self.fail_after = -1
        self._n = 0

    def sendall(self, data: bytes) -> None:  # noqa: ANN001
        if self.fail_after >= 0 and self._n >= self.fail_after:
            raise ConnectionError("simulated drop")
        self._n += 1
        self.sent.append(data)


def test_mrb2615_drain_connection_error_requeues_failed_line_first(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    sock = _RecordingSock()
    sock.fail_after = 1  # first send ok, second raises
    s.sock = sock
    s._out_q.put(("bob-tm", "out id=aabbccdd seq=1 A"))
    s._out_q.put(("bob-tm", "out id=aabbccdd seq=2 B"))
    s._out_q.put(("bob-tm", "DONE id=aabbccdd exit=0"))
    try:
        s.drain_out_queue()
        assert False, "expected ConnectionError"
    except ConnectionError:
        pass
    assert s._force_reconnect is True
    # Failed line + remainder must still be queued (failed line first).
    assert s.out_queue_size() == 2
    n1, p1 = s._out_q.get_nowait()
    n2, p2 = s._out_q.get_nowait()
    assert (n1, p1) == ("bob-tm", "out id=aabbccdd seq=2 B")
    assert (n2, p2) == ("bob-tm", "DONE id=aabbccdd exit=0")


def test_mrb2615_done_line_clears_inflight_via_track(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    s.sock = _RecordingSock()
    s._on_console_out("bob-tm", "out id=cf38f565 seq=1 LINE1")
    assert s.shell_inflight().get("bob-tm") == "cf38f565"
    s._on_console_out("bob-tm", "DONE id=cf38f565 exit=0")
    assert "bob-tm" not in s.shell_inflight()


def test_mrb2615_flush_stop_noop_when_idle(tmp_path, monkeypatch):
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.0)
    sock = _RecordingSock()
    s.sock = sock
    s.flush_stop_dones(reason="probe interrupted")
    assert sock.sent == []
    assert s.out_queue_size() == 0


def test_mrb2615_read_loop_stop_paths_call_flush():
    src = Path(svc.__file__).read_text(encoding="utf-8")
    assert 'flush_stop_dones(reason="probe interrupted")' in src
    assert 'flush_stop_dones(reason="reap interrupted")' in src
    assert src.count("flush_stop_dones") >= 2


def test_mrb2615_skill_bullets_contiguous():
    root = Path(svc.__file__).resolve().parents[1]
    skill = (root / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "Long Command output / reconnect (FR #2612)" in skill
    assert "outbound queue that survives in-process `force_reconnect`" in skill
    trouble = (
        root / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "Long Command stalls after `out … seq=1`" in trouble
    assert "FR #2612" in trouble

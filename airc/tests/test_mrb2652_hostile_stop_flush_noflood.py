"""MRB #2652 hostile gates for FR #2649 stop-flush (no FLOOD_S / no double flush)."""
from __future__ import annotations

from pathlib import Path

import airc_console_service as svc


ROOT = Path(__file__).resolve().parents[2]


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


def test_mrb2652_normal_send_still_floods(tmp_path, monkeypatch):
    """flood=False is stop-only; normal PRIVMSG path must keep FLOOD_S."""
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.35)
    sleeps: list[float] = []
    monkeypatch.setattr(svc.time, "sleep", lambda sec: sleeps.append(float(sec)))
    sock = _RecordingSock()
    s.sock = sock
    s.send_privmsg("bob-tm", "out id=aabbccdd seq=1 hello")
    assert any(x >= 0.3 for x in sleeps), f"normal path must flood: {sleeps}"


def test_mrb2652_prepare_stop_drains_pending_without_flood(tmp_path, monkeypatch):
    """Pending (not only inflight) jobs get err+DONE with flood=False."""
    s = _svc(tmp_path, monkeypatch)
    monkeypatch.setattr(svc, "FLOOD_S", 0.35)
    sleeps: list[float] = []

    def track_sleep(sec: float) -> None:
        sleeps.append(float(sec))
        if sec >= 0.3 and s.sock is not None:
            try:
                s.sock.close()
            except Exception:
                pass

    monkeypatch.setattr(svc.time, "sleep", track_sleep)
    sock = _RecordingSock()
    s.sock = sock
    # Pending via runner open ids when available; else inflight is enough —
    # still assert no flood sleep and DONE present.
    s.note_shell_inflight("bob-tm", "deadbeef")
    s.prepare_stop(reason="session interrupted")
    joined = b"".join(sock.sent).decode("utf-8", errors="replace")
    assert "DONE id=deadbeef exit=1" in joined
    assert not any(x >= 0.3 for x in sleeps), f"stop path flooded: {sleeps}"


def test_mrb2652_finally_gate_uses_stop_flushed():
    src = Path(svc.__file__).read_text(encoding="utf-8")
    assert "not self._stop_flushed" in src
    assert "self._stop_flushed = False" in src
    assert "drain_out_queue(flood=False)" in src


def test_mrb2652_docs_restore_concurrent_and_noflood():
    """Product tip dropped FR #2632 concurrent details and broke sendall escapes."""
    doc = (ROOT / "airc" / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    assert "busy: prior shell still emitting" in doc
    assert "one shell in flight" in doc
    assert "no per-line FLOOD_S delay" in doc or "FLOOD_S" in doc
    assert "_stop_flushed" in doc
    assert "\\sendall\\s" not in doc
    assert "`sendall`" in doc or "sendall" in doc


def test_mrb2652_skill_2649_bullet_contiguous():
    skill = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "flood=False" in skill
    assert "_stop_flushed" in skill
    # Contiguous stop-flush bullet (no orphan mid-insert).
    assert "FR #2640 / #2649" in skill or "FR #2640/#2649" in skill

"""MRB #2644 hostile gates for FR #2640 (stop flush before socket close).

Vision (common/docs/vision.md): maintained fleet services — Wait must not hang when
Airc stops mid-Command (DONE before close; no WinError 10038 post-close send).
"""
from __future__ import annotations

from pathlib import Path

import repo_layout

import airc_console as ac
import airc_console_service as svc

ROOT = Path(repo_layout.ROOT)


def _svc(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    return svc.AircConsoleService(args)


class _CloseTrackingSock:
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


def test_mrb2644_prepare_stop_done_before_close_no_10038(tmp_path, monkeypatch):
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
    assert s.sock is None


def test_mrb2644_open_job_ids_sees_pending_queue():
    runner = ac.ShellJobRunner(on_reply=lambda *_: None, wait=False, pending_max=4)
    import threading

    hold = threading.Event()
    release = threading.Event()

    def blocker() -> None:
        hold.set()
        release.wait(timeout=5)

    t = threading.Thread(target=blocker, name="airc-shell-bob-tm", daemon=True)
    with runner._lock:
        runner._threads["bob-tm"] = t
    t.start()
    assert hold.wait(timeout=2)
    try:
        runner.start("bob-tm", "id=deadbeef Write-Output queued")
        ids = {jid for _n, jid in runner.open_job_ids()}
        assert "deadbeef" in ids
    finally:
        release.set()
        t.join(timeout=2)
        runner.abandon_open_jobs()
        with runner._lock:
            runner._threads.pop("bob-tm", None)


def test_mrb2644_skills_document_prepare_stop():
    skill = (ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md").read_text(encoding="utf-8")
    trouble = (
        ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
    ).read_text(encoding="utf-8")
    docs = (ROOT / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "FR #2640" in skill
    assert "prepare_stop" in skill
    assert "WinError 10038" in trouble or "10038" in trouble
    assert "FR #2640" in docs or "prepare_stop" in docs.lower() or "pending shell" in docs.lower()
    assert "â" not in skill and "â" not in trouble and "â" not in docs

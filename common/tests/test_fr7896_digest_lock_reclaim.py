"""FR #7896: a live ear reclaims a digest.lock left by a dead publish thread."""
from __future__ import annotations

import threading
from pathlib import Path

import bobreport
import irc_agent


def test_dead_holder_thread_is_reclaimed(tmp_path: Path):
    def _leak() -> None:
        bobreport.abandon_digest_lock_for_tests(tmp_path)

    holder = threading.Thread(target=_leak)
    holder.start()
    holder.join(5)
    assert not holder.is_alive()
    marker = tmp_path / "published.txt"
    with bobreport.digest_lock(tmp_path):
        marker.write_text("ok", encoding="ascii")
    assert marker.read_text(encoding="ascii") == "ok"


def test_disk_full_releases_lock_and_reports(tmp_path: Path, monkeypatch):
    filed: list[str] = []

    def _report(component, exc, *, site="", **_kw):
        filed.append(site)
        return {"ok": True}

    import runtime_failure

    monkeypatch.setattr(runtime_failure, "report", _report)

    def _once() -> None:
        with bobreport.digest_lock(tmp_path):
            raise OSError(28, "No space left on device")

    try:
        _once()
    except OSError:
        pass
    assert filed == ["digest-publish-enospc"]
    with bobreport.digest_lock(tmp_path):
        (tmp_path / "digest-write.txt").write_text("resumed", encoding="ascii")
    assert (tmp_path / "digest-write.txt").read_text(encoding="ascii") == "resumed"
    try:
        _once()
    except OSError:
        pass
    assert filed == ["digest-publish-enospc", "digest-publish-enospc"]


def test_watchdog_restarts_stopped_loop_once(tmp_path: Path, monkeypatch):
    filed: list[str] = []

    def _msg(component, message, *, site=""):
        filed.append(site)
        return {"ok": True}

    import runtime_failure

    monkeypatch.setattr(runtime_failure, "report_message", _msg)

    class Ear:
        home = tmp_path
        sock = object()
        dead = threading.Event()
        stop = threading.Event()
        _publish_loop_reported = False
        _outbox_gen = 1
        loops = 0

        def outbox_loop(self, gen):
            self.loops += 1
            self.stop.wait(2)

    ear = Ear()
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    ear._outbox_thread = dead
    assert irc_agent.Client.watch_publish_loop(ear) is True
    assert ear.loops == 1
    assert filed == ["digest-publish-loop-dead"]
    assert irc_agent.Client.watch_publish_loop(ear) is False
    assert filed == ["digest-publish-loop-dead"]
    ear.stop.set()
    ear._outbox_thread.join(2)

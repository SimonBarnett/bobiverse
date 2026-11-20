"""FR #8481: same-pid skills-sync lock must wait, not busy-spin."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import sync_install_skills as sis


def test_fr8481_same_pid_open_lock_waits_for_deadline(tmp_path: Path) -> None:
    install = tmp_path / "install"
    run = install / "run"
    run.mkdir(parents=True)
    (install / ".git").mkdir()
    lock = run / sis.LOCK_NAME
    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, ("%s\n" % os.getpid()).encode("ascii"))
    box: dict = {}

    def _run() -> None:
        box["held"] = sis._acquire_skills_sync_lock(install, 0.2)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(2.0)
    try:
        assert not thread.is_alive()
        assert box.get("held") is None
        assert lock.is_file()
    finally:
        os.close(fd)

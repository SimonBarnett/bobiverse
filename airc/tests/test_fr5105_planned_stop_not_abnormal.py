"""FR #5105: planned UPDATE/NSSM stop must not file abnormal-exit; attach real log tail."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
COMMON = Path(__file__).resolve().parents[2] / "common" / "scripts"
for p in (str(SCRIPTS), str(COMMON)):
    if p not in sys.path:
        sys.path.insert(0, p)

import airc_intake_event as ev  # noqa: E402


def test_restarting_stamp_is_not_abnormal(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_MACHINE_ID", "marchhare")
    posts: list[str] = []

    def fake_post(title, body, **kw):
        posts.append(kw.get("sig") or "")
        return {"ok": True}

    ev.mark_restarting(tmp_path)
    r = ev.note_previous_abnormal_exit(tmp_path, filer_post=fake_post)
    assert r is None
    assert posts == []
    assert ev.read_stamp(tmp_path) == "running"


def test_log_tail_reads_install_logs_dir(tmp_path):
    home = tmp_path / "home"
    logs = tmp_path / "logs"
    home.mkdir()
    logs.mkdir()
    (logs / "airc-console.log").write_text("INFO session ok\nINFO last line\n", encoding="utf-8")
    tail = ev._log_tail(home)
    assert "last line" in tail
    assert "(none)" not in tail


def test_updater_stamps_restarting_before_airc_stop():
    text = (COMMON / "Update-BobiverseService.ps1").read_text(encoding="utf-8")
    assert "FR #5105" in text
    assert "airc-run.stamp" in text
    assert text.index("FR #5105") < text.index("service-stopped $ServiceName")

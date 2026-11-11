"""FR #6481: planned service-stop signals must not file abnormal-exit on next start.

Redqueen 2026-11-11: keepalive-only tail then NSSM/restart with stamp=running filed
abnormal-exit. Orderly SIGINT/SIGBREAK / atexit / main KeyboardInterrupt / early
no-password exit must stamp clean or restarting so the next boot stays quiet.
Hard kill (no handler) still reports abnormal-exit.

MRB #6482: SIGINT/SIGBREAK handler must stamp then raise KeyboardInterrupt so
FR #2541 prepare_stop paths still run (must not swallow the signal).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
COMMON = Path(__file__).resolve().parents[2] / "common" / "scripts"
for pth in (str(SCRIPTS), str(COMMON)):
    if pth not in sys.path:
        sys.path.insert(0, pth)

import airc_intake_event as ev  # noqa: E402


def test_fr6481_sigint_marks_restarting_not_abnormal(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_MACHINE_ID", "redqueen")
    posts: list[str] = []

    def fake_post(title, body, **kw):
        posts.append(kw.get("sig") or "")
        return {"ok": True}

    ev.write_stamp(tmp_path, "running")
    ev.install_stop_stamp_handlers(tmp_path)
    # Simulate NSSM/console CTRL_C / SIGINT before process exit.
    with pytest.raises(KeyboardInterrupt):
        ev._stop_stamp_on_signal(None, None)
    assert ev.read_stamp(tmp_path) == "restarting"
    r = ev.note_previous_abnormal_exit(tmp_path, filer_post=fake_post)
    assert r is None
    assert posts == []


def test_fr6481_sigint_handler_does_not_swallow_interrupt(tmp_path):
    """Hostile: stamp then raise - never return normally after SIGINT."""
    ev.write_stamp(tmp_path, "running")
    ev.install_stop_stamp_handlers(tmp_path)
    raised = False
    try:
        ev._stop_stamp_on_signal(2, None)
    except KeyboardInterrupt:
        raised = True
    assert raised is True
    assert ev.read_stamp(tmp_path) == "restarting"
    # Handler source must raise (string pin against swallow-only regressions).
    src = (SCRIPTS / "airc_intake_event.py").read_text(encoding="utf-8")
    assert "raise KeyboardInterrupt" in src
    idx = src.index("def _stop_stamp_on_signal")
    window = src[idx : idx + 700]
    assert "raise KeyboardInterrupt" in window
    assert "mark_restarting" in window


def test_fr6481_atexit_marks_clean_when_still_running(tmp_path):
    ev.write_stamp(tmp_path, "running")
    ev.install_stop_stamp_handlers(tmp_path)
    ev._atexit_mark_clean_if_running()
    assert ev.read_stamp(tmp_path) == "clean"


def test_fr6481_hard_kill_still_abnormal(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_MACHINE_ID", "redqueen")
    posts: list[str] = []

    def fake_post(title, body, **kw):
        posts.append(kw.get("sig") or "")
        return {"ok": True}

    # No stop handler ran (TerminateProcess / power loss).
    ev.write_stamp(tmp_path, "running")
    r = ev.note_previous_abnormal_exit(tmp_path, filer_post=fake_post)
    assert r is not None
    assert posts == ["airc|redqueen|abnormal-exit"]


def test_fr6481_service_source_installs_handlers_and_main_clean():
    src = (SCRIPTS / "airc_console_service.py").read_text(encoding="utf-8")
    assert "install_stop_stamp_handlers" in src
    assert "FR #6481" in src
    assert "mark_clean_exit" in src
    # main KeyboardInterrupt and early no-password exit must not leave stamp=running.
    assert src.count("mark_clean_exit") >= 2

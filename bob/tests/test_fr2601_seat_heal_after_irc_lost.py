"""FR #2601 history + FR #3180: seat starts are manual only (seat-heal removed).

FR #2601 introduced TipForm seat-heal after irc-lost. FR #3180 makes starts
manual only: Watchdog must not Launch, Ensure is report-only, docs say so.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
START_WORKER = ROOT / "bob" / "tray" / "tools" / "BobTrayStartWorker.ps1"
WORKER_PY = ROOT / "bob" / "scripts" / "bob_worker.py"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobWorkerSeats.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr2601_irc_lost_is_exit_3():
    t = _read(WORKER_PY)
    assert "EXIT_IRC_LOST = 3" in t
    assert "irc-lost:" in t


def test_fr2601_tray_seat_heal_removed_by_fr3180():
    t = _read(BOB_TRAY)
    wd = t[t.find("void Watchdog()") :]
    wd = wd[: wd.find("\n        void ", 1)] if "\n        void " in wd[1:] else wd
    assert "HealEngine()" in wd
    assert "HealWorkerSeats" not in wd
    assert "WorkerLauncher.Launch" not in wd
    assert "ObserveWorkerSeats" in wd or "seat-exit" in t
    assert "void HealWorkerSeats" not in t


def test_fr2601_hard_cap_2_still_shared():
    t = _read(BOB_TRAY)
    assert "MaxWorkers = 2" in t
    assert "SeatsMissing" in t


def test_fr2601_ensure_script_report_only_and_docs():
    assert ENSURE.is_file(), "Ensure-BobWorkerSeats.ps1 missing"
    ens = _read(ENSURE)
    assert "FR #3180" in ens or "report-only" in ens.lower()
    assert "Measure-BobTrayWorkerSeats -Procs" in ens
    assert "req-" not in ens or "never" in ens.lower()
    post = _read(POST)
    assert "FR #3180" in post
    assert "manual only" in post.lower() or "manual-only" in post.lower()


def test_fr2601_startworker_cap_helpers_still_shared():
    t = _read(START_WORKER)
    assert "BobTrayHardMaxWorkers = 2" in t
    assert "Measure-BobTrayWorkerSeats" in t

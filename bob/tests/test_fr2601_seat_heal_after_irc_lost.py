"""FR #2601: TipForm tops agent seats back up to hard cap 2 after irc-lost exits.

Evidence from MarchHare seat 15152: worker.log ended with
  irc: LOST connection closed by server
  worker: shutting down (irc-lost: ...) exit=3
Crash hook does not apply (clean irc-lost). Gap: nothing restarted the seat.
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


def test_fr2601_tray_seat_heal_in_watchdog():
    t = _read(BOB_TRAY)
    assert "FR #2601" in t
    assert "HealWorkerSeats" in t or "seat-heal" in t
    assert "BOBIVERSE_WORKER_SEAT_HEAL" in t
    assert "SeatHealEnabled" in t or "WORKER_SEAT_HEAL" in t
    # Watchdog must heal seats even when the engine is still alive.
    wd = t[t.find("void Watchdog()") :]
    wd = wd[: wd.find("\n        void ", 1)] if "\n        void " in wd[1:] else wd
    assert "HealWorkerSeats" in wd or "seat-heal" in wd
    # Must not return early solely because engine is alive before seat heal.
    engine_return = wd.find("if (engine != null && !engine.HasExited) return;")
    if engine_return >= 0:
        # Old pattern must be gone, or seat heal must run before that return.
        heal_idx = wd.find("HealWorkerSeats")
        assert heal_idx >= 0
        assert heal_idx < engine_return or "HealEngine" in wd


def test_fr2601_seat_heal_respects_hard_cap_2():
    t = _read(BOB_TRAY)
    assert "MaxWorkers = 2" in t
    assert "SeatsMissing" in t
    body = t[t.find("void HealWorkerSeats") :]
    body = body[: body.find("\n        void ", 1)] if "\n        void " in body[1:] else body
    assert 'Launch(root, "agent"' in body
    assert "plan" not in body


def test_fr2601_ensure_script_and_docs():
    assert ENSURE.is_file(), "Ensure-BobWorkerSeats.ps1 missing"
    ens = _read(ENSURE)
    assert "FR #2601" in ens
    assert "Measure-BobTrayWorkerSeats" in ens or "BobTrayHardMaxWorkers" in ens
    assert "DryRun" in ens or "dry-run" in ens.lower() or "$DryRun" in ens
    # Must pass -Procs (bare Measure with no list always reports 0).
    assert "Measure-BobTrayWorkerSeats -Procs" in ens
    post = _read(POST)
    assert "FR #2601" in post or "seat-heal" in post or "Ensure-BobWorkerSeats" in post


def test_fr2601_startworker_cap_helpers_still_shared():
    t = _read(START_WORKER)
    assert "BobTrayHardMaxWorkers = 2" in t
    assert "Measure-BobTrayWorkerSeats" in t

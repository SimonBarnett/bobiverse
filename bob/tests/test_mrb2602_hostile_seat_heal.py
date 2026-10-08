"""MRB #2602 history + FR #3180: seat-heal removed; manual-only gates.

Locks Watchdog HealEngine-only, no HealWorkerSeats Launch, Ensure report-only,
and docs/skill FR #3180 markers.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
ENSURE = ROOT / "bob" / "scripts" / "Ensure-BobWorkerSeats.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
WORKER_PY = ROOT / "bob" / "scripts" / "bob_worker.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2602_watchdog_heals_engine_not_seats():
    t = _read(BOB_TRAY)
    wd = t[t.find("void Watchdog()") :]
    wd = wd[: wd.find("\n        void ", 1)] if "\n        void " in wd[1:] else wd
    assert "HealEngine()" in wd
    assert "HealWorkerSeats()" not in wd
    assert "ObserveWorkerSeats" in wd or "seat-exit" in t


def test_mrb2602_no_heal_worker_seats_launch_path():
    t = _read(BOB_TRAY)
    assert "MaxWorkers = 2" in t
    assert "void HealWorkerSeats" not in t
    assert "seat-exit" in t
    assert "not restarted" in t


def test_mrb2602_launch_cap_refusal_still_gates():
    t = _read(BOB_TRAY)
    i = t.find("public static int Launch(string")
    assert i >= 0
    launch = t[i:]
    launch = launch[: launch.find("\n        public static", 1)] if "\n        public static" in launch[1:] else launch
    assert "CapRefusal(mode)" in launch or "CapRefusal()" in launch


def test_mrb2602_ensure_report_only():
    ens = _read(ENSURE)
    assert "FR #3180" in ens or "report-only" in ens.lower()
    assert "Measure-BobTrayWorkerSeats -Procs" in ens
    assert "$DryRun" in ens
    assert "Set-Content" not in ens
    assert "Move-Item" not in ens or "req-" not in ens


def test_mrb2602_irc_lost_exit_3_and_docs_skill():
    assert "EXIT_IRC_LOST = 3" in _read(WORKER_PY)
    post = _read(POST)
    assert "FR #3180" in post and "manual only" in post.lower()
    skill = _read(SKILL)
    assert "FR #3180" in skill
    assert "manual only" in skill.lower()
    assert "HealWorkerSeats" not in skill

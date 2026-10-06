"""MRB #2602 hostile: TipForm seat-heal after bob-worker irc-lost (FR #2601).

Product PR #2602 landed HealWorkerSeats + Ensure-BobWorkerSeats.ps1.
These gates lock Watchdog split, agent-only Launch, hard cap 2, opt-out,
Measure -Procs, and seat-heal lifecycle / docs markers.
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


def test_mrb2602_watchdog_calls_heal_engine_and_seats():
    t = _read(BOB_TRAY)
    wd = t[t.find("void Watchdog()") :]
    wd = wd[: wd.find("\n        void ", 1)] if "\n        void " in wd[1:] else wd
    assert "HealEngine()" in wd
    assert "HealWorkerSeats()" in wd
    # Old early-return that skipped seat heal when engine was alive must be gone from Watchdog.
    assert "if (engine != null && !engine.HasExited) return;" not in wd


def test_mrb2602_heal_worker_seats_agent_only_cap2_opt_out():
    t = _read(BOB_TRAY)
    assert "MaxWorkers = 2" in t
    assert "BOBIVERSE_WORKER_SEAT_HEAL" in t
    assert "SeatHealEnabled" in t
    body = t[t.find("void HealWorkerSeats") :]
    body = body[: body.find("\n        void ", 1)] if "\n        void " in body[1:] else body
    assert 'Launch(root, "agent"' in body
    assert '"plan"' not in body
    assert "seat-heal" in body
    assert "seatHeals >= 3" in body or "seatHeals>3" in body.replace(" ", "")


def test_mrb2602_launch_cap_refusal_still_gates():
    t = _read(BOB_TRAY)
    launch = t[t.find("public static int Launch") :]
    launch = launch[: launch.find("\n        public static", 1)] if "\n        public static" in launch[1:] else launch
    # Launch gates on CapRefusal(mode); bare CapRefusal() remains on the --seats text path.
    assert "CapRefusal(mode)" in launch or "CapRefusal()" in launch


def test_mrb2602_ensure_script_measure_procs_dryrun_opt_out():
    ens = _read(ENSURE)
    assert "FR #2601" in ens
    assert "Measure-BobTrayWorkerSeats -Procs" in ens
    assert "$DryRun" in ens
    assert "BOBIVERSE_WORKER_SEAT_HEAL" in ens
    assert "mode    = 'agent'" in ens or "mode='agent'" in ens.replace(" ", "")
    assert "Never queues Plan seats" in ens or "never queues Plan" in ens


def test_mrb2602_irc_lost_exit_3_and_docs_skill():
    assert "EXIT_IRC_LOST = 3" in _read(WORKER_PY)
    post = _read(POST)
    assert "FR #2601" in post and "seat-heal" in post and "Ensure-BobWorkerSeats" in post
    skill = _read(SKILL)
    assert "FR #2601" in skill or "seat-heal" in skill
    assert "BOBIVERSE_WORKER_SEAT_HEAL" in skill

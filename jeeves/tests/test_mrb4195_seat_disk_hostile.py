"""MRB #4195 hostile pins for FR #4192 SeatDisk-after-JobWorktrees.

Pins contiguous skill/script phrases so a mid-bullet splice cannot drop the
SeatDisk-before-intake order or the worker-seat FR #4192 line.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JOBS = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
SEAT = REPO / "common" / "scripts" / "Clear-BobiverseSeatDisk.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
WORKER_SEAT = (
    REPO
    / "bob"
    / "agents"
    / "worker"
    / ".grok"
    / "skills"
    / "bobiverse-worker-seat"
    / "SKILL.md"
)


def test_job_worktrees_warn_contiguous_seat_disk_reclaim():
    text = JOBS.read_text(encoding="utf-8")
    # Contiguous playbook: name SeatDisk -Reclaim in the low-disk WARN.
    assert "Clear-BobiverseSeatDisk.ps1 -Reclaim" in text
    assert "FR #4192" in text
    assert "Never hand-delete C:\\ai\\* wt trees (FR #2727)" in text


def test_seat_disk_warn_after_reclaim_contiguous():
    text = SEAT.read_text(encoding="utf-8")
    assert "FR #4192: FreeGB=" in text or "FR #4192: FreeGB={" in text
    # PS double-quoted WARN escapes backslashes as C:\\ai\\* in source.
    assert "do not hand-delete C:\\\\ai\\\\* wt trees (FR #2727)" in text
    assert "KeepTempHours" in text
    assert "pytest-of-*" in text


def test_fr_skill_seat_disk_before_intake_contiguous():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "FR #4192 (after JobWorktrees still low)" in text
    assert "Clear-BobiverseSeatDisk.ps1 -Reclaim" in text
    assert "before** filing intake" in text or "before filing intake" in text


def test_worker_seat_skill_pins_fr4192_before_intake():
    text = WORKER_SEAT.read_text(encoding="utf-8")
    assert "run SeatDisk -Reclaim **before** filing a disk-capacity intake (FR #4192)" in text

"""MRB #6579 hostile: FR #6563 seat marker alone is not local work."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLEAR_PS1 = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
PIN = ROOT / "jeeves" / "tests" / "test_fr3641_clear_seat_marker_protect.py"


def test_mrb6579_clear_defines_seat_only_dirt_helper():
    src = CLEAR_PS1.read_text(encoding="utf-8")
    assert "function Test-BobiverseSeatOnlyDirt" in src
    assert ".bobiverse-seat" in src
    assert "FR #6563" in src
    assert "ClearToolProcs" in src
    assert "meaningful" in src
    assert not CLEAR_PS1.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6579_seat_only_dirt_matches_bob_scratch():
    src = CLEAR_PS1.read_text(encoding="utf-8")
    i = src.find("function Test-BobiverseSeatOnlyDirt")
    assert i >= 0
    window = src[i : i + 900]
    assert ".bobiverse-seat" in window
    assert ".bob/*" in window or ".bob\\*" in window
    assert "return $true" in window
    assert "return $false" in window


def test_mrb6579_force_pin_isolates_job_worktree_base():
    pin = PIN.read_text(encoding="utf-8")
    assert "BOB_JOB_WORKTREE_BASE" in pin
    assert "monkeypatch.setenv" in pin
    assert "wt-base" in pin
    assert "FR #6563" in pin
    assert not PIN.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6579_tool_proc_cache_reset_each_clear():
    src = CLEAR_PS1.read_text(encoding="utf-8")
    assert "$script:ClearToolProcs = $null" in src
    assert "if ($null -eq $script:ClearToolProcs)" in src

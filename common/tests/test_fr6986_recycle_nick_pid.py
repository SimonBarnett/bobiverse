"""FR #6986: stall-heal recycle must resolve pid from seat nick when the marker is missing."""
from __future__ import annotations

from pathlib import Path

import recycleseat as rs

PS1 = (
    Path(__file__).resolve().parents[2]
    / "bob"
    / "tray"
    / "tools"
    / "BobTrayRecycleSeat.ps1"
)


def test_pid_from_seat_nick_redqueen():
    assert rs.pid_from_seat_nick("redqueen-7376") == 7376
    assert rs.pid_from_seat_nick("flamingo-17568") == 17568
    assert rs.pid_from_seat_nick("bob-redqueen") == 0
    assert rs.pid_from_seat_nick("") == 0


def test_resolve_recycle_pid_prefers_marker_then_nick():
    assert rs.resolve_recycle_pid(4242, "redqueen-7376") == 4242
    assert rs.resolve_recycle_pid(0, "redqueen-7376") == 7376
    assert rs.resolve_recycle_pid(0, "not-a-seat") == 0


def test_missing_marker_with_nick_pid_is_found():
    """Replay: same nick survives recycle because tray treated marker-miss as not-found."""
    pid = rs.resolve_recycle_pid(0, "redqueen-7376")
    assert pid == 7376
    may, reason = rs.plan_recycle_action(
        stop_ok=True, target_still_alive=False, target_found=pid > 0
    )
    assert (may, reason) == (True, "ok")


def test_tray_ps1_falls_back_to_nick_pid():
    t = PS1.read_text(encoding="utf-8-sig")
    assert "FR #6986" in t
    assert "Get-BobTraySeatPidFromNick" in t
    assert "resolve_recycle_pid" in t or "SeatPidFromNick" in t

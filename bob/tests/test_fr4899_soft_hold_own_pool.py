"""FR #4899: soft out-of-fuel hold clears only on the seat's own fuel pool.

A grok seat with grok_pct=0 exhausted must stay held even when the machine's
Cursor pool still has tokens (cursor_low>0). PR #4859 hardened hard-402 only;
the soft-hold branch still used ``cursor_has_tokens or grok_has_tokens``.
"""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_soft_hold_helper_grok_stays_held_when_only_cursor_has_tokens():
    fuel = bw.Fuel(
        grok_pct=0,
        grok_state="exhausted",
        cursor_high=100,
        cursor_low=27,
    )
    ok, why = bw.out_of_fuel_reading_clears_soft_hold(fuel, kind="grok")
    assert ok is False
    assert why == ""


def test_soft_hold_helper_grok_clears_on_own_pct():
    fuel = bw.Fuel(grok_pct=20, grok_state="available", cursor_low=0)
    ok, why = bw.out_of_fuel_reading_clears_soft_hold(fuel, kind="grok")
    assert ok is True
    assert "kind=grok" in why
    assert "pct=20" in why


def test_soft_hold_helper_cursor_clears_on_own_pool():
    fuel = bw.Fuel(grok_pct=0, grok_state="exhausted", cursor_low=27)
    ok, why = bw.out_of_fuel_reading_clears_soft_hold(fuel, kind="cursor")
    assert ok is True
    assert "kind=cursor" in why
    assert "27" in why


def test_soft_hold_helper_grok_session_key_clears():
    fuel = bw.Fuel(grok_pct=0, grok_state="exhausted", cursor_low=27)
    ok, why = bw.out_of_fuel_reading_clears_soft_hold(
        fuel, kind="grok", has_session_key=True
    )
    assert ok is True
    assert "session key" in why


def test_soft_hold_helper_kind_switch_to_cursor_logs():
    fuel = bw.Fuel(grok_pct=0, grok_state="exhausted", cursor_low=27)
    ok, why = bw.out_of_fuel_reading_clears_soft_hold(
        fuel, kind="grok", allow_cursor_kind_switch=True
    )
    assert ok is True
    assert "kind-switch to cursor" in why


def test_fuel_available_again_soft_grok_ignores_cursor_pool(monkeypatch, tmp_path: Path):
    class Bored:
        _out_of_fuel_hard_402 = False
        _out_of_fuel_clear_reason = None

    class Seat:
        kind = "grok"
        secret = None
        bored = Bored()

        def _install_root_for_fuel(self):
            return tmp_path

    seat = Seat()
    monkeypatch.setattr(
        bw,
        "read_fuel",
        lambda *a, **kw: bw.Fuel(
            grok_pct=0, grok_state="exhausted", cursor_high=100, cursor_low=27
        ),
    )
    assert bw.Supervisor._fuel_available_again(seat) is False
    assert seat.bored._out_of_fuel_clear_reason is None


def test_fuel_available_again_soft_grok_clears_on_pct(monkeypatch, tmp_path: Path):
    class Bored:
        _out_of_fuel_hard_402 = False
        _out_of_fuel_clear_reason = None

    class Seat:
        kind = "grok"
        secret = None
        bored = Bored()

        def _install_root_for_fuel(self):
            return tmp_path

    seat = Seat()
    monkeypatch.setattr(
        bw,
        "read_fuel",
        lambda *a, **kw: bw.Fuel(grok_pct=20, grok_state="available", cursor_low=0),
    )
    assert bw.Supervisor._fuel_available_again(seat) is True
    assert "kind=grok" in (seat.bored._out_of_fuel_clear_reason or "")
    assert "pct=20" in (seat.bored._out_of_fuel_clear_reason or "")


def test_fuel_available_again_soft_cursor_clears(monkeypatch, tmp_path: Path):
    class Bored:
        _out_of_fuel_hard_402 = False
        _out_of_fuel_clear_reason = None

    class Seat:
        kind = "cursor"
        secret = None
        bored = Bored()

        def _install_root_for_fuel(self):
            return tmp_path

    seat = Seat()
    monkeypatch.setattr(
        bw,
        "read_fuel",
        lambda *a, **kw: bw.Fuel(grok_pct=0, grok_state="exhausted", cursor_low=27),
    )
    assert bw.Supervisor._fuel_available_again(seat) is True
    assert "kind=cursor" in (seat.bored._out_of_fuel_clear_reason or "")

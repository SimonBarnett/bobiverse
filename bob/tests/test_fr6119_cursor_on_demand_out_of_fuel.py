"""FR #6119: Cursor on-demand spend limit is out-of-fuel (not done-miss churn).

Acceptance:
(a) Fuel parses on_demand_* / overspend_state from Get-BobAgentFuel JSON
(b) cursor_high>0 but on_demand at-limit => fuel_explicitly_exhausted + no cursor_has_tokens
(c) mid-job poll GIVEUPs out-of-fuel on at-limit readings (flamingo class: high=100 low=0)
(d) two fast done-miss releases (<60s ACK lifetime) enter out-of-fuel hold (no !bored)
(e) Get-BobAgentFuel.ps1 surfaces on_demand fields from LocalCursorDoc
(f) bobiverse-bob-worker skill names FR #6119 / on-demand
"""
from __future__ import annotations

import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait

ROOT = Path(__file__).resolve().parents[1]
FUEL_PS1 = ROOT / "tray" / "tools" / "Get-BobAgentFuel.ps1"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"


def test_a_parse_fuel_on_demand_fields():
    raw = (
        '{"ok":true,"cursor":{"high":100,"low":0,"any":100,'
        '"on_demand_used_cents":20011,"on_demand_limit_cents":20000,'
        '"on_demand_remaining_pct":0,"overspend_state":"at-limit"},'
        '"grok":{"remaining_pct":0,"state":"exhausted"}}\n'
    )
    f = bw.parse_fuel(raw)
    assert f.cursor_high == 100 and f.cursor_low == 0
    assert f.on_demand_used_cents == 20011
    assert f.on_demand_limit_cents == 20000
    assert f.on_demand_remaining_pct == 0
    assert f.overspend_state == "at-limit"


def test_b_cursor_on_demand_at_limit_overrides_pool_remain():
    """flamingo class: high=100 low=0 but spend limit hit => exhausted."""
    f = bw.Fuel(
        cursor_high=100,
        cursor_low=0,
        grok_pct=0,
        grok_state="exhausted",
        on_demand_used_cents=20011,
        on_demand_limit_cents=20000,
        on_demand_remaining_pct=0,
        overspend_state="at-limit",
    )
    assert bw.cursor_on_demand_at_limit(f) is True
    assert bw.cursor_has_tokens(f) is False
    assert bw.fuel_reading_known(f, "cursor") is True
    assert bw.fuel_explicitly_exhausted(f, "cursor") is True
    snap = bw.format_fuel_reading(f, "cursor")
    assert "on_demand" in snap or "at-limit" in snap
    assert "exhausted=True" in snap


def test_b_on_demand_used_ge_limit_without_state_string():
    f = bw.Fuel(
        cursor_high=50,
        cursor_low=10,
        on_demand_used_cents=20000,
        on_demand_limit_cents=20000,
    )
    assert bw.cursor_on_demand_at_limit(f) is True
    assert bw.fuel_explicitly_exhausted(f, "cursor") is True


def test_b_on_demand_under_limit_keeps_tokens():
    f = bw.Fuel(
        cursor_high=12,
        cursor_low=0,
        on_demand_used_cents=500,
        on_demand_limit_cents=20000,
        on_demand_remaining_pct=97,
        overspend_state="over",
    )
    assert bw.cursor_on_demand_at_limit(f) is False
    assert bw.cursor_has_tokens(f) is True
    assert bw.fuel_explicitly_exhausted(f, "cursor") is False


def test_b_select_agent_skips_cursor_when_on_demand_at_limit():
    f = bw.Fuel(
        cursor_high=100,
        cursor_low=0,
        grok_pct=0,
        grok_state="exhausted",
        on_demand_used_cents=20011,
        on_demand_limit_cents=20000,
        overspend_state="at-limit",
    )
    d = bw.select_agent(f, cursor_cmd=r"C:\cursor\agent.cmd", grok_exe=r"C:\grok\agent.exe")
    assert d.kind != "cursor"


def test_c_mid_job_on_demand_at_limit_giveup():
    clock = FakeClock(0.0)
    released: list[str] = []
    f = bw.Fuel(
        cursor_high=100,
        cursor_low=0,
        on_demand_used_cents=20011,
        on_demand_limit_cents=20000,
        overspend_state="at-limit",
    )

    e, sent, logs = _emitter(clock, idle_s=120.0)
    e.fuel_poll_s = 5.0
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.fuel_lost_check_fn = lambda: bw.fuel_explicitly_exhausted(f, "cursor")
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#6110")
    clock.advance(1.0)
    clock.advance(5.5)
    time.sleep(0.05)
    assert released == []
    clock.advance(5.5)
    assert _wait(lambda: len(released) == 1, clock, timeout=3.0), (released, logs)
    assert released == ["GIVEUP MRB SimonBarnett/bobiverse#6110 out-of-fuel"]
    assert e.out_of_fuel is True
    n0 = len(e.sent)
    clock.advance(60.0)
    time.sleep(0.05)
    assert not any(r in ("idle", "nak", "done-miss") for _, r in e.sent[n0:])
    e.stop()


def test_d_two_fast_done_miss_enter_out_of_fuel():
    """Two short ACK->done-miss reminder releases enter out-of-fuel (stop !bored churn)."""
    clock = FakeClock(0.0)
    released: list[str] = []
    e, sent, logs = _emitter(clock, idle_s=120.0)
    e.done_miss_grace_s = 1.0
    e.fast_done_miss_s = 60.0
    e.fast_done_miss_need = 2
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))

    def _fast_release(job: str) -> None:
        e.on_outbox(f"ACK MRB {job}")
        clock.advance(0.5)  # ACK age well under fast_done_miss_s
        with e._cv:
            e._done_miss_reminded = True
            e._done_miss_armed_at = clock()
            e._done_miss_key = f"MRB {job}"
        e.turn_ended()
        clock.advance(0.1)

    _fast_release("o/r#6110")
    assert e.out_of_fuel is False
    assert e.fast_done_miss_streak == 1
    assert released == []
    # First release cleared ACK via done-miss path; start a fresh ACK for streak 2.
    _fast_release("o/r#6111")
    assert _wait(lambda: e.out_of_fuel is True, clock, timeout=2.0), (
        e.out_of_fuel,
        e.fast_done_miss_streak,
        released,
        logs[-20:],
    )
    assert e.fast_done_miss_streak >= 2
    assert released == ["GIVEUP MRB o/r#6111 out-of-fuel"]
    assert any("fast-done-miss" in m for m in logs)
    n0 = len(e.sent)
    clock.advance(90.0)
    time.sleep(0.05)
    assert not any(r in ("idle", "nak", "done-miss") for _, r in e.sent[n0:])
    e.stop()


def test_e_get_bob_agent_fuel_ps1_surfaces_on_demand():
    text = FUEL_PS1.read_text(encoding="utf-8")
    assert "on_demand_used_cents" in text
    assert "on_demand_limit_cents" in text
    assert "on_demand_remaining_pct" in text
    assert "overspend_state" in text


def test_f_skill_fr6119_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8")
    assert "FR #6119" in t
    assert "on-demand" in t.lower() or "on_demand" in t.lower()


def test_hostile_remaining_pct_zero_with_cents_left_is_not_at_limit():
    """Rounded remain_pct=0 must not override used < limit (CodeRabbit / Get-CursorAgentUsage round)."""
    f = bw.Fuel(
        cursor_high=100,
        cursor_low=0,
        on_demand_used_cents=19950,
        on_demand_limit_cents=20000,
        on_demand_remaining_pct=0,
    )
    assert bw.cursor_on_demand_at_limit(f) is False
    assert bw.fuel_explicitly_exhausted(f, "cursor") is False
    assert bw.cursor_has_tokens(f) is True


def test_hostile_incomplete_on_demand_fields_not_mid_job_exhausted():
    """Limit-only / pool-null readings are known for selection but must not mid-job GIVEUP."""
    limit_only = bw.Fuel(on_demand_limit_cents=20000)
    assert bw.fuel_reading_known(limit_only, "cursor") is True
    assert bw.cursor_on_demand_at_limit(limit_only) is False
    assert bw.fuel_explicitly_exhausted(limit_only, "cursor") is False

    under = bw.Fuel(
        cursor_high=None,
        cursor_low=None,
        on_demand_used_cents=100,
        on_demand_limit_cents=20000,
        overspend_state="ok",
    )
    assert bw.fuel_reading_known(under, "cursor") is True
    assert bw.fuel_explicitly_exhausted(under, "cursor") is False


def test_hostile_soft_out_of_fuel_hold_not_cleared_by_turn_ended():
    """FR #4858 clears hard-402 only; fast-done-miss soft hold must survive turn_ended."""
    clock = FakeClock(0.0)
    e, sent, logs = _emitter(clock, idle_s=120.0)
    e.note_out_of_fuel("fast-done-miss streak=2 key=MRB o/r#1")
    assert e.out_of_fuel is True
    assert bool(getattr(e, "_out_of_fuel_hard_402", False)) is False
    e.turn_ended()
    clock.advance(0.1)
    assert e.out_of_fuel is True
    e.stop()


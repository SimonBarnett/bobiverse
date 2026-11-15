"""FR #7485: explicit --agent never silently starts a different agent.

Flamingo incident: tray launched ``--agent opencode`` with xAI expired and
Cursor fuel remaining; opencode binary missing; worker started Cursor.
"""
from __future__ import annotations

import json
from pathlib import Path

import bob.scripts.bob_worker as bw

CUR, GRK, OP = r"C:\c\agent.cmd", r"C:\g\agent.exe", r"C:\o\opencode.exe"


def _fuel(**kwargs):
    base = dict(
        grok_pct=0,
        cursor_high=None,
        cursor_low=57,
        grok_state="exhausted",
        opencode_free=100,
        opencode_go=None,
    )
    base.update(kwargs)
    return bw.Fuel(**base)


def test_fr7485_explicit_opencode_missing_binary_refuses_despite_cursor_fuel():
    """No opencode.exe + Cursor fuel + expired xAI => refuse, never cursor."""
    fuel = _fuel()
    auto = bw.select_agent(fuel, CUR, GRK, None, xai_signin_ok=False)
    assert auto.kind == "cursor"  # auto path may still pick Cursor
    dec = bw.resolve_seat_decision(
        "opencode",
        auto,
        fuel,
        CUR,
        GRK,
        None,  # opencode missing
        auth_present=True,
        xai_signin_ok=False,
    )
    assert dec.kind == "refuse"
    assert "opencode" in dec.reason.lower()
    assert dec.kind != "cursor"


def test_fr7485_explicit_opencode_with_fuel_starts_opencode_not_cursor():
    fuel = _fuel(opencode_free=100, cursor_low=90, grok_pct=99, grok_state="available")
    auto = bw.select_agent(fuel, CUR, GRK, OP, xai_signin_ok=True)
    assert auto.kind == "grok"
    dec = bw.resolve_seat_decision(
        "opencode", auto, fuel, CUR, GRK, OP, auth_present=False, xai_signin_ok=True
    )
    assert dec.kind == "opencode"


def test_fr7485_explicit_opencode_go_paid_needs_auth_not_cursor():
    fuel = _fuel(opencode_free=0, opencode_go=50, cursor_low=90)
    auto = bw.select_agent(fuel, CUR, GRK, OP, xai_signin_ok=False)
    dec = bw.resolve_seat_decision(
        "opencode", auto, fuel, CUR, GRK, OP, auth_present=False, xai_signin_ok=False
    )
    assert dec.kind == "refuse"
    assert "auth.json" in dec.reason


def test_fr7485_explicit_cursor_and_grok_mappings():
    fuel = _fuel(grok_pct=40, grok_state="available", cursor_low=10)
    auto = bw.select_agent(fuel, CUR, GRK, OP, xai_signin_ok=True)
    cur = bw.resolve_seat_decision(
        "cursor", auto, fuel, CUR, GRK, OP, auth_present=True, xai_signin_ok=True
    )
    assert cur.kind == "cursor"
    grok = bw.resolve_seat_decision(
        "grok", auto, fuel, CUR, GRK, OP, auth_present=True, xai_signin_ok=True
    )
    assert grok.kind == "grok"


def test_fr7485_explicit_grok_expired_refuses_does_not_start_cursor():
    fuel = _fuel(grok_pct=40, grok_state="available", cursor_low=57)
    auto = bw.select_agent(fuel, CUR, GRK, OP, xai_signin_ok=False)
    assert auto.kind == "cursor"
    dec = bw.resolve_seat_decision(
        "grok", auto, fuel, CUR, GRK, OP, auth_present=True, xai_signin_ok=False
    )
    assert dec.kind in ("refuse", "xai-auth-expired")
    assert dec.kind != "cursor"
    assert dec.kind != "opencode"


def test_fr7485_auto_still_falls_through_when_agent_omitted():
    fuel = _fuel()
    auto = bw.select_agent(fuel, CUR, GRK, OP, xai_signin_ok=False)
    dec = bw.resolve_seat_decision(
        "", auto, fuel, CUR, GRK, OP, auth_present=True, xai_signin_ok=False
    )
    assert dec.kind == "cursor"


def test_fr7485_apply_xai_gate_does_not_rewrite_refuse():
    fuel = _fuel()
    refused = bw.Decision("refuse", "explicit opencode: opencode.exe missing")
    out = bw.apply_xai_signin_gate(
        refused, fuel, CUR, GRK, None, signin_ok=False
    )
    assert out.kind == "refuse"


def test_fr7485_dry_run_explicit_opencode_missing_refuses(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: GRK)
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: CUR)
    monkeypatch.setattr(bw, "resolve_opencode_cmd", lambda *a, **k: None)
    monkeypatch.setattr(bw, "read_fuel", lambda *a, **k: _fuel())
    monkeypatch.setattr(bw, "opencode_auth_file_present", lambda env=None: True)
    monkeypatch.setattr(bw, "preflight_xai_signin", lambda *a, **k: "expired")
    code = bw.main(["--dry-run", "--install-root", str(tmp_path), "--agent", "opencode"])
    assert code == bw.EXIT_OK
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["decision"] == "refuse"
    assert payload["agent"] == "opencode"
    assert payload["decision"] != "cursor"

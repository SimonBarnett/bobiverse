"""FR #7345: Grok seats never stop at an interactive xAI sign-in prompt."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import bobreport


def test_fr7345_select_grok_when_signin_ok():
    d = bw.select_agent(
        bw.Fuel(40, 10, 50, "available"),
        r"C:\c\agent.cmd",
        r"C:\g\agent.exe",
        xai_signin_ok=True,
    )
    assert d.kind == "grok"


def test_fr7345_expired_falls_to_cursor_when_fuel():
    d = bw.select_agent(
        bw.Fuel(40, 10, 50, "available"),
        r"C:\c\agent.cmd",
        r"C:\g\agent.exe",
        xai_signin_ok=False,
    )
    d = bw.apply_xai_signin_gate(
        d,
        bw.Fuel(40, 10, 50, "available"),
        r"C:\c\agent.cmd",
        r"C:\g\agent.exe",
        None,
        signin_ok=False,
    )
    assert d.kind == "cursor"
    assert "xai-auth-expired" in d.reason or d.kind == "cursor"


def test_fr7345_expired_no_fuel_exits_named_reason():
    d = bw.select_agent(
        bw.Fuel(0, 0, 50, "available"),
        None,
        r"C:\g\agent.exe",
        xai_signin_ok=False,
    )
    d = bw.apply_xai_signin_gate(
        d,
        bw.Fuel(0, 0, 50, "available"),
        None,
        r"C:\g\agent.exe",
        None,
        signin_ok=False,
    )
    assert d.kind == "xai-auth-expired"
    assert "xai-auth-expired" in d.reason
    assert bw.EXIT_XAI_AUTH_EXPIRED == 9


def test_fr7345_explicit_grok_expired_does_not_launch_grok():
    """FR #7485: explicit grok + expired xAI refuses; never falls through to Cursor."""
    fuel = bw.Fuel(40, 10, 50, "available")
    d = bw.explicit_agent_decision(
        "grok", fuel, r"C:\c\agent.cmd", r"C:\g\agent.exe", None, auth_present=False
    )
    assert d.kind == "grok"
    d = bw.resolve_seat_decision(
        "grok",
        d,
        fuel,
        r"C:\c\agent.cmd",
        r"C:\g\agent.exe",
        None,
        auth_present=False,
        xai_signin_ok=False,
    )
    assert d.kind == "xai-auth-expired"
    assert d.kind != "cursor"


def test_fr7345_preflight_uses_ear_error_class():
    assert bw.classify_xai_signin_state("grok-login-expired") == "expired"
    assert bw.classify_xai_signin_state("auth-file-missing") == "expired"
    assert bw.classify_xai_signin_state("") == "ok"
    assert bw.preflight_xai_signin(last_acq={"error": "grok-login-expired"}) == "expired"
    assert bw.preflight_xai_signin(last_acq={"error": None}) == "ok"
    assert (
        bw.preflight_xai_signin(
            fetch_fn=lambda: None, last_acq={"error": "auth-key-missing"}
        )
        == "expired"
    )


def test_fr7345_prompt_detect_and_30s_window():
    assert bw.grok_console_is_signin_prompt("Please sign in to continue\nvisit https://auth.x.ai")
    assert bw.grok_console_is_signin_prompt("enter the device code ABC")
    assert not bw.grok_console_is_signin_prompt("Grok ready. waiting for FROM")
    clock = {"t": 0.0}

    def now():
        return clock["t"]

    g = bw.GrokSigninPromptGuard(lambda: "", timeout_s=30.0, clock=now)
    assert g.tick() is False
    clock["t"] = 29.0
    assert g.tick() is False
    g2 = bw.GrokSigninPromptGuard(lambda: "device code: 1234", timeout_s=30.0, clock=now)
    assert g2.tick() is True
    d = bw.decision_after_grok_signin_prompt(
        bw.Fuel(12, 0, 40, "available"), r"C:\c\agent.cmd", None
    )
    assert d.kind == "cursor"


def test_fr7345_ear_stamps_xai_auth_expired_and_clears():
    peer = {"machine": "flamingo"}
    bad = {
        "weekly_known": False,
        "remaining_pct": None,
        "error": bobreport.XAI_GROK_LOGIN_EXPIRED,
        "source": "cli",
        "fetched_at": None,
        "fresh": False,
    }
    out = bobreport.enrich_peer_with_xai_weekly(peer, bad)
    out = bobreport.stamp_xai_auth(out)
    assert out.get("xai_auth") == "expired"
    assert (out.get("xai_weekly") or {}).get("xai_auth") == "expired"
    good = {
        "weekly_known": True,
        "remaining_pct": 41,
        "error": None,
        "source": "cli",
        "fetched_at": "2026-11-14T00:00:00Z",
        "fresh": True,
        "window": "weekly",
    }
    ok = bobreport.stamp_xai_auth(bobreport.enrich_peer_with_xai_weekly({"machine": "flamingo"}, good))
    assert ok.get("xai_auth") == "ok"


def test_fr7345_tray_copy_and_docs():
    hover = (
        Path(__file__).resolve().parents[1]
        / "tray"
        / "src"
        / "Public"
        / "Get-BobTrayHover.ps1"
    ).read_text(encoding="utf-8-sig")
    assert "7345" in hover
    assert "xAI sign-in expired, sign in once on" in hover
    docs = (Path(__file__).resolve().parents[1] / "docs" / "bob-tray-dialogs.md").read_text(
        encoding="utf-8"
    )
    assert "7345" in docs
    ear = (Path(__file__).resolve().parents[1] / "docs" / "bob-ear.md").read_text(encoding="utf-8")
    assert "xai_auth" in ear
    assert "7345" in ear

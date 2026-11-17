"""FR #8111: airc wss keepalive every 30s (Cloudflare ~100s idle cut)."""
from __future__ import annotations

import time

import airc_console_service as svc


def test_idle_ping_seconds_wss_default_30():
    assert svc.idle_ping_seconds("wss wsirc.ntsa.uk", env={}) == 30.0
    assert svc.idle_ping_seconds("WSS label", env={}) == 30.0


def test_idle_ping_seconds_tls_stays_60():
    assert svc.idle_ping_seconds("tls irc.ntsa.uk:993", env={}) == 60.0
    # WSS env must not change tls.
    assert (
        svc.idle_ping_seconds(
            "tls irc.ntsa.uk:6697",
            env={svc.AIRC_WSS_PING_ENV: "15"},
        )
        == 60.0
    )


def test_idle_ping_seconds_env_override_and_clamp():
    assert (
        svc.idle_ping_seconds("wss x", env={svc.AIRC_WSS_PING_ENV: "45"}) == 45.0
    )
    # Never exceed 60 on wss even if misconfigured.
    assert (
        svc.idle_ping_seconds("wss x", env={svc.AIRC_WSS_PING_ENV: "90"}) == 60.0
    )
    assert (
        svc.idle_ping_seconds("wss x", env={svc.AIRC_WSS_PING_ENV: "0"}) == 30.0
    )
    assert (
        svc.idle_ping_seconds("wss x", env={svc.AIRC_WSS_PING_ENV: "nope"})
        == 30.0
    )


def _keepalive_stub(*, transport: str, idle_s: float) -> tuple[svc.AircConsoleService, list[str]]:
    s = svc.AircConsoleService.__new__(svc.AircConsoleService)
    s._registered = True
    s._transport_desc = transport
    s._last_recv = time.monotonic() - idle_s
    s._last_ping_sent = 0.0
    s._awaiting_pong = False
    s._force_reconnect = False
    sent: list[str] = []
    s.send = sent.append  # type: ignore[method-assign]
    s._names_sync_watchdog = lambda: None  # type: ignore[method-assign]
    s._auth_wedge_watchdog = lambda: None  # type: ignore[method-assign]
    return s, sent


def test_wss_schedules_first_ping_by_30s_after_registration():
    """Quiet wss after 001: first PING once idle reaches 30s (not 60)."""
    s29, sent29 = _keepalive_stub(transport="wss wsirc.ntsa.uk", idle_s=29.0)
    s29._idle_keepalive()
    assert sent29 == []
    assert s29._awaiting_pong is False

    s30, sent30 = _keepalive_stub(transport="wss wsirc.ntsa.uk", idle_s=30.0)
    s30._idle_keepalive()
    assert len(sent30) == 1
    assert sent30[0].upper().startswith("PING ")
    assert s30._awaiting_pong is True

    # Second cycle after PONG traffic: another 30s of silence -> another PING.
    s30._awaiting_pong = False
    s30._last_recv = time.monotonic() - 30.0
    s30._idle_keepalive()
    assert len(sent30) == 2


def test_tls_still_waits_60s():
    s45, sent45 = _keepalive_stub(transport="tls irc.ntsa.uk:993", idle_s=45.0)
    s45._idle_keepalive()
    assert sent45 == []

    s60, sent60 = _keepalive_stub(transport="tls irc.ntsa.uk:993", idle_s=60.0)
    s60._idle_keepalive()
    assert len(sent60) == 1
    assert sent60[0].upper().startswith("PING ")

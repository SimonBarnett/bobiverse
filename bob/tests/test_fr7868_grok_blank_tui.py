# -*- coding: utf-8 -*-
"""FR #7868: a black Grok console is reported after 120s and is not recycled."""
from __future__ import annotations

import bob_worker as bw


def test_fr7868_border_fragment_is_blank_and_chrome_is_not():
    assert bw.grok_console_has_tui_chrome("") is False
    assert bw.grok_console_has_tui_chrome("+--+") is False
    assert bw.grok_console_has_tui_chrome("grok >") is True


def test_fr7868_blank_for_120s_reports_once_and_does_not_kill():
    now = {"t": 0.0}
    reports = []
    killed = []

    def clock():
        return now["t"]

    guard = bw.GrokBlankTuiGuard(
        lambda: "+--+",
        window_s=120.0,
        clock=clock,
        report=lambda: reports.append("grok-blank-tui"),
        log=lambda _s: None,
    )
    assert guard.tick() is False
    now["t"] = 119.0
    assert guard.tick() is False
    assert reports == []
    now["t"] = 120.0
    assert guard.tick() is True
    assert guard.tick() is True
    assert reports == ["grok-blank-tui"]
    assert killed == []


def test_fr7868_chrome_before_window_does_not_report():
    now = {"t": 0.0}
    reports = []
    screen = {"t": ""}

    guard = bw.GrokBlankTuiGuard(
        lambda: screen["t"],
        window_s=120.0,
        clock=lambda: now["t"],
        report=lambda: reports.append("x"),
    )
    screen["t"] = "You are Grok"
    now["t"] = 200.0
    assert guard.tick() is False
    assert guard.rendered is True
    assert reports == []

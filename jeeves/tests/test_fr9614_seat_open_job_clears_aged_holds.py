# -*- coding: utf-8 -*-
"""FR #9614: seat_open_job must purge aged pins with clear_aged_live_holds=True."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO


def test_fr9614_seat_open_job_passes_clear_aged_live_holds_true():
    src = (REPO / "common" / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    start = src.index("def seat_open_job(")
    end = src.index("\ndef ", start + 1)
    window = src[start:end]
    assert "clear_aged_live_holds=True" in window
    assert "clear_aged_live_holds=False" not in window
    assert "9614" in window or "9565" in window

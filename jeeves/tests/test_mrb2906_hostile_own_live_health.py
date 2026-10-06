"""Hostile pins for MRB #2906 / FR #2902 own-live digest.lock health.

Product already on main via #2906. Pins contiguous skill + code phrases.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-troubleshooting" / "SKILL.md"
CALLBACK = ROOT / "common" / "scripts" / "bobcallback.py"
REPORT = ROOT / "common" / "scripts" / "bobreport.py"


def test_mrb2906_skill_pins_fr2902():
    text = SKILL.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "FR #2902" in text
    assert "lock_own" in text
    assert "left own live digest.lock" in text
    assert "git-claim" in text and "digest.lock" in text


def test_mrb2906_code_pins_own_live_and_git_claim_off_lock():
    cb = CALLBACK.read_text(encoding="utf-8")
    br = REPORT.read_text(encoding="utf-8")
    assert "lock_own" in cb
    assert "_watchdog_try_break" in cb
    assert "left own live digest.lock" in cb
    assert "own live holder never trips lock_ok" in cb or "or own_live" in cb
    assert "_apply_callback_digest" in br
    assert "git-claim" in br and "must not run under" in br
    assert "digest-lock-heartbeat" in br or "heartbeat every 10s" in br

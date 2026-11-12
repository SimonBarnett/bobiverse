"""Hostile MRB #6739: VISION S2 one-window hermetic test must force keys inject.

Bare sys.stdin.readline children do not expand clipboard; default paste (Ctrl+V)
delivers literal "v". The S2 measurement must set BOB_WORKER_INJECT_PASTE=0.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

S2 = ROOT / "bob" / "tests" / "test_bob_worker_020.py"


def test_mrb6739_s2_one_window_forces_inject_paste_zero():
    text = S2.read_text(encoding="utf-8")
    assert "test_one_window_agent_shares_our_console_and_gets_injected_input" in text
    # Host script must force keys before inject_console (not ambient-only).
    assert "BOB_WORKER_INJECT_PASTE" in text
    assert "os.environ['BOB_WORKER_INJECT_PASTE'] = '0'" in text or (
        'os.environ["BOB_WORKER_INJECT_PASTE"] = "0"' in text
    )
    # Must appear inside the one-window host payload, not only in unrelated tests.
    idx = text.index("test_one_window_agent_shares_our_console_and_gets_injected_input")
    chunk = text[idx : idx + 2500]
    assert "BOB_WORKER_INJECT_PASTE" in chunk
    assert "inject_console" in chunk

"""FR #9691: Soft-deprecate bob-worker --mode monitor in favor of --mode jeeves.

The monitor mode still works but logs a deprecation warning and shows a
deprecation message in the prompt. Users should migrate to --mode jeeves.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BW = Path(__file__).resolve().parents[1] / "scripts" / "bob_worker.py"  # bob/scripts


def test_bob_worker_mode_monitor_is_marked_deprecated():
    """FR #9691: Mode monitor is marked as deprecated in docstring."""
    t = BW.read_text(encoding="utf-8-sig")
    # Check that the docstring has [DEPRECATED] marker
    assert "[DEPRECATED - use --mode jeeves]" in t
    # Check that it references FR #9691
    assert "FR #9691" in t


def test_bob_worker_run_monitor_has_deprecation_warning():
    """FR #9691: run_monitor logs a deprecation warning."""
    t = BW.read_text(encoding="utf-8-sig")
    # Find the run_monitor function
    assert "def run_monitor" in t
    # Check that it has the deprecation warning log
    assert 'log("WARNING: --mode monitor is deprecated' in t or "log('WARNING: --mode monitor is deprecated" in t
    # Check that it mentions FR #9691
    assert "FR #9691" in t


def test_bob_worker_monitor_prompt_has_deprecation_message():
    """FR #9691: monitor_prompt includes deprecation message for the user."""
    t = BW.read_text(encoding="utf-8-sig")
    # Find the monitor_prompt function
    assert "def monitor_prompt" in t
    # Check that the prompt has the deprecation marker
    assert "[DEPRECATED - FR #9691]" in t or "[DEPRECATED" in t and "mode jeeves" in t
    # Check that it mentions --mode jeeves as the alternative
    assert "--mode jeeves" in t


def test_bob_worker_monitor_mode_still_in_choices():
    """FR #9691: monitor mode is still available (soft deprecation, not removal)."""
    t = BW.read_text(encoding="utf-8-sig")
    # Check that monitor is still in the choices tuple
    assert re.search(r'choices=\(["\']agent["\'],.*["\']monitor["\']', t) or \
           re.search(r'choices=.*["\']monitor["\'].*agent', t)
    # monitor should be in the mode lines
    assert '--mode monitor' in t


def test_bob_worker_jeeves_mode_is_alternative():
    """FR #9691: jeeves mode exists and is documented as the replacement."""
    t = BW.read_text(encoding="utf-8-sig")
    # Check that jeeves mode exists
    assert '--mode jeeves' in t
    assert 'FR #9640' in t  # FR that introduced jeeves mode
    # mode branch uses mode_l == "jeeves" (not args.mode == "jeeves")
    assert 'mode_l == "jeeves"' in t
    assert '"jeeves"' in t and '_WORKER_EXE_MODES' in t

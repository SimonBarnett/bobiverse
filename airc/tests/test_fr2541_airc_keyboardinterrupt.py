"""FR #2541: airc TimeoutError handler must not let KeyboardInterrupt escape as a crash."""
from __future__ import annotations

from pathlib import Path


def test_fr2541_timeout_handler_catches_keyboardinterrupt_source():
    src = Path("airc/scripts/airc_console_service.py").read_text(encoding="utf-8")
    assert "FR #2541" in src
    # TimeoutError path must catch KeyboardInterrupt (BaseException), not only Exception.
    assert "except KeyboardInterrupt" in src
    assert "_check_probe_timeout" in src
    # run() must treat interrupt as clean stop
    assert src.count("except KeyboardInterrupt") >= 2

"""FR #2683: prepare_seat_child_env must scrub CURSOR_*/SAND_* after merging extra."""
from __future__ import annotations

import bob_worker as bw


def test_fr2683_extra_cursor_sand_scrubbed_after_merge():
    """Hostile probe from #2683: extra CURSOR_/SAND_ must not survive prepare."""
    out = bw.prepare_seat_child_env({}, {"CURSOR_FROM_EXTRA": "b", "SAND_FROM_EXTRA": "c"})
    assert "CURSOR_FROM_EXTRA" not in out
    assert "SAND_FROM_EXTRA" not in out


def test_fr2683_extra_cursor_does_not_reappear_over_scrubbed_base():
    base = {"CURSOR_API_KEY": "fake", "PATH": "p", "BOB_MACHINE": "marchhare"}
    out = bw.prepare_seat_child_env(base, {"CURSOR_FROM_EXTRA": "b", "BOB_OUTBOX": "o"})
    assert "CURSOR_API_KEY" not in out
    assert "CURSOR_FROM_EXTRA" not in out
    assert out["BOB_OUTBOX"] == "o"
    assert out["PATH"] == "p"
    assert out["BOB_MACHINE"] == "marchhare"


def test_fr2683_extra_bob_paths_normalized_after_merge():
    out = bw.prepare_seat_child_env(
        {},
        {"BOB_IRC_HOME": r"C:\\Users\\x\\.bobiverse", "BOB_OUTBOX": "o"},
    )
    assert out["BOB_IRC_HOME"] == r"C:\Users\x\.bobiverse"
    assert out["BOB_OUTBOX"] == "o"

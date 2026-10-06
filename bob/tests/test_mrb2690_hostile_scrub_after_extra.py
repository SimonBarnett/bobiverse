"""MRB #2690 hostile: prepare_seat_child_env scrub+normalise after extra merge (FR #2683)."""
from __future__ import annotations

import bob_worker as bw


def test_mrb2690_mixed_case_cursor_sand_in_extra_scrubbed():
    out = bw.prepare_seat_child_env(
        {"PATH": "p"},
        {"cursor_api_key": "x", "Sand_Token": "y", "CuRsOr_FROM_EXTRA": "z"},
    )
    assert "cursor_api_key" not in out
    assert "Sand_Token" not in out
    assert "CuRsOr_FROM_EXTRA" not in out
    assert out["PATH"] == "p"


def test_mrb2690_does_not_mutate_base_or_extra():
    base = {"CURSOR_API_KEY": "fake", "BOB_MACHINE": "m"}
    extra = {"CURSOR_FROM_EXTRA": "b", "BOB_OUTBOX": "o"}
    base_snap = dict(base)
    extra_snap = dict(extra)
    out = bw.prepare_seat_child_env(base, extra)
    assert base == base_snap
    assert extra == extra_snap
    assert "CURSOR_API_KEY" not in out
    assert "CURSOR_FROM_EXTRA" not in out
    assert out["BOB_OUTBOX"] == "o"


def test_mrb2690_seat_env_extra_plus_hostile_overlay():
    seat = bw.seat_env_extra(r"C:\run\seat", "MarchHare", "marchhare-1")
    hostile = dict(seat)
    hostile["CURSOR_INJECT"] = "leak"
    hostile["SAND_INJECT"] = "leak"
    out = bw.prepare_seat_child_env({"CURSOR_PARENT": "1", "PATH": "p"}, hostile)
    assert "CURSOR_PARENT" not in out
    assert "CURSOR_INJECT" not in out
    assert "SAND_INJECT" not in out
    assert out["BOB_OUTBOX"].endswith("outbox.txt")
    assert out["BOB_SHOP"] == "#MarchHare" or out["BOB_MACHINE"] == "marchhare"
    assert out["PATH"] == "p"


def test_mrb2690_none_and_empty_extra_still_scrub_base():
    base = {"CURSOR_X": "1", "SAND_Y": "2", "KEEP": "z"}
    assert "CURSOR_X" not in bw.prepare_seat_child_env(base, None)
    assert "SAND_Y" not in bw.prepare_seat_child_env(base, {})
    assert bw.prepare_seat_child_env(base, None)["KEEP"] == "z"


def test_mrb2690_extra_doubled_bob_path_normalized_after_merge():
    out = bw.prepare_seat_child_env(
        {"BOB_HOME": r"C:\Users\a\.bob"},
        {"BOB_IRC_HOME": r"C:\\Users\\b\\.bobiverse", "CURSOR_SKIP": "1"},
    )
    assert out["BOB_IRC_HOME"] == r"C:\Users\b\.bobiverse"
    assert out["BOB_HOME"] == r"C:\Users\a\.bob"
    assert "CURSOR_SKIP" not in out

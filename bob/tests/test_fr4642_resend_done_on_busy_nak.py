"""FR #4642: NAK busy (held X) re-sends the DONE this seat already emitted for X."""
from __future__ import annotations

from bob_worker import (
    busy_nak_held_job,
    replay_done_line_for_busy_nak,
)


def test_busy_nak_held_job_parses_addressed_line():
    text = "marchhare-13128: NAK !BORED busy (held FIX SimonBarnett/a-search#3359)"
    assert busy_nak_held_job(text) == "FIX SimonBarnett/a-search#3359"


def test_replay_matches_last_done_only():
    nak = "marchhare-13128: NAK !BORED busy (held FIX SimonBarnett/a-search#3359)"
    done = "DONE FIX SimonBarnett/a-search#3359 PASS https://github.com/SimonBarnett/a-search/pull/3359"
    assert replay_done_line_for_busy_nak(nak, done) == done
    assert replay_done_line_for_busy_nak(nak, "DONE FR SimonBarnett/bobiverse#1 https://github.com/SimonBarnett/bobiverse/pull/1") == ""
    assert replay_done_line_for_busy_nak("marchhare-13128: NAK !BORED busy", done) == ""

"""FR #8415: DONE already in the outbox is not no-ack-after-assign."""
from __future__ import annotations

import bob.scripts.bob_worker as bw

DONE = "DONE MRB SimonBarnett/bobiverse#8239 FAIL https://github.com/SimonBarnett/bobiverse/pull/8239\n"
TURNS = (
    '{"type":"turn_ended","error_class":"epipe","status":"error"}\n'
)


def test_done_plus_epipe_is_not_no_ack():
    reason = bw.ack_miss_exit_reason(
        outbox_text=DONE,
        turns_text=TURNS,
        job_key="MRB SimonBarnett/bobiverse#8239",
    )
    assert reason == "epipe"
    assert reason != "no-ack-after-assign"


def test_done_without_turn_class_is_done_posted():
    reason = bw.ack_miss_exit_reason(
        outbox_text=DONE,
        turns_text="",
        job_key="MRB SimonBarnett/bobiverse#8239",
    )
    assert reason == "done-posted"


def test_empty_outbox_stays_no_ack_path():
    assert bw.ack_miss_exit_reason(outbox_text="", turns_text=TURNS, job_key="MRB x#1") is None

"""FR #2383: assign injected + no run-dir ACK → outbox reminder, then seat recycle."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_looks_like_job_assign_detects_fr_mrb_uat():
    line = (
        "FROM Jeeves #marchhare marchhare-40208: FR SimonBarnett/bobiverse#2383 "
        "https://github.com/SimonBarnett/bobiverse/issues/2383 "
        "[outbox: C:\\run\\outbox.txt]"
    )
    assert bw.looks_like_job_assign(line, "marchhare-40208")
    assert bw.looks_like_job_assign(
        "FROM Jeeves #m m-1: MRB o/r#1 https://example/pull/1", "m-1"
    )
    assert not bw.looks_like_job_assign(
        "FROM Jeeves #m m-1: nothing queued", "m-1"
    )


def test_assign_ack_miss_remind_then_recycle():
    miss = bw.AssignAckMiss(remind_s=10.0, recycle_s=30.0)
    assign = "FROM Jeeves #marchhare marchhare-1: FR o/r#9 https://example/issues/9"
    miss.note_inject(assign, 100.0, own_nick="marchhare-1")
    assert miss.tick(105.0, ack_open=False) is None
    assert miss.tick(111.0, ack_open=False) == "remind"
    assert miss.tick(120.0, ack_open=False) is None
    assert miss.tick(131.0, ack_open=False) == "recycle"


def test_assign_ack_miss_clears_on_ack():
    miss = bw.AssignAckMiss(remind_s=10.0, recycle_s=30.0)
    miss.note_inject(
        "FROM Jeeves #m m-1: FR o/r#1 https://x/issues/1", 0.0, own_nick="m-1"
    )
    assert miss.tick(11.0, ack_open=False) == "remind"
    miss.note_ack()
    assert miss.tick(40.0, ack_open=False) is None
    assert miss.tick(12.0, ack_open=True) is None


def test_nothing_queued_does_not_arm_miss():
    miss = bw.AssignAckMiss(remind_s=10.0, recycle_s=30.0)
    miss.note_inject(
        "FROM Jeeves #m m-1: nothing queued", 0.0, own_nick="m-1"
    )
    assert miss.tick(100.0, ack_open=False) is None


def test_reminder_line_carries_outbox_footer(tmp_path: Path):
    miss = bw.AssignAckMiss(remind_s=1.0, recycle_s=2.0)
    out = tmp_path / "outbox.txt"
    line = miss.reminder_line(shop="#marchhare", outbox=out)
    assert line.startswith("FROM bob-worker #marchhare ")
    assert "BOB_OUTBOX" in line
    assert "[outbox:" in line
    assert str(out) in line
    assert "home\\outbox" in line

def test_nothing_queued_clears_armed_miss():
    """MRB #2386: withdrawn idle wire must disarm remind/recycle."""
    miss = bw.AssignAckMiss(remind_s=10.0, recycle_s=30.0)
    miss.note_inject(
        "FROM Jeeves #m m-1: FR o/r#1 https://x/issues/1", 0.0, own_nick="m-1"
    )
    assert miss.tick(11.0, ack_open=False) == "remind"
    miss.note_inject(
        "FROM Jeeves #m m-1: nothing queued", 12.0, own_nick="m-1"
    )
    assert miss.tick(50.0, ack_open=False) is None


def test_on_outbox_wire_nack_clears_ack_miss():
    class _Bored:
        def on_outbox(self, payload):
            self.last = payload

    class _Sup:
        def __init__(self):
            self.ack_miss = bw.AssignAckMiss(remind_s=10.0, recycle_s=30.0)
            self.bored = _Bored()
            self.ack_miss.note_inject(
                "FROM Jeeves #m m-1: MRB o/r#9 https://x/pull/9", 0.0, own_nick="m-1"
            )
            assert self.ack_miss.tick(11.0, ack_open=False) == "remind"

        def on_outbox_wire(self, payload: str) -> None:
            p = (payload or "").strip()
            if bw._OUT_ACK_RX.match(p) or bw._OUT_DONE_RX.match(p) or bw._OUT_FREE_RX.match(p):
                self.ack_miss.note_ack()
            if self.bored:
                self.bored.on_outbox(payload)

    s = _Sup()
    s.on_outbox_wire("NACK MRB o/r#9")
    assert s.ack_miss.tick(40.0, ack_open=False) is None


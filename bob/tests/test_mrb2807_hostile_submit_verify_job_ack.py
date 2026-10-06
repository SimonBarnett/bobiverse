"""MRB #2807 hostile pins for FR #2791 submit-verify job-matched ACK stop."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


class _NewlineEnterTui:
    def __init__(self, newline_enters: int = 2):
        self.newline_left = int(newline_enters)
        self.box = ""
        self.pastes: list[str] = []
        self.submitted: list[str] = []

    def inject(self, pid, text, submit_gap_s=None):
        self.pastes.append(text)
        self.box = text
        self.enter()
        self.enter()
        return True

    def enter(self, pid=0):
        if self.newline_left > 0:
            self.newline_left -= 1
            self.box += "\n"
            return True
        if self.box:
            self.submitted.append(self.box)
            self.box = ""
        return True


def _stop_for_line(bored: bw.BoredEmitter, line: str):
    want = bw.assign_job_ref(line)
    if not want:
        return None
    return lambda b=bored, w=want: bool(b.ack_open) and (b.ack_job_ref == w)


def test_mrb2807_preexisting_matching_ack_stops_immediately():
    """Already-open ACK for the same job must stop at once (no retries)."""
    tui = _NewlineEnterTui(2)
    clock = [0.0]
    logs: list[str] = []
    b = bw.BoredEmitter(lambda: True, lambda m: None, clock=lambda: clock[0])
    b.on_outbox("ACK MRB SimonBarnett/bobiverse#200")
    line = (
        "FROM Jeeves #marchhare marchhare-1: MRB SimonBarnett/bobiverse#200 "
        "https://github.com/SimonBarnett/bobiverse/pull/200"
    )
    ok = bw.inject_with_submit_verify(
        1,
        line,
        inject_fn=tui.inject,
        enter_fn=tui.enter,
        probe_fn=lambda: bool(tui.submitted),
        clock=lambda: clock[0],
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        log=logs.append,
        verify_s=3.0,
        max_retries=3,
        backoffs=(3.0, 5.0, 8.0),
        stop_fn=_stop_for_line(b, line),
        sync=True,
    )
    assert ok is True
    assert any("(stop/ACK)" in m for m in logs)
    assert not any("submit-verify retry=" in m for m in logs)
    assert clock[0] == 0.0
    assert len(tui.pastes) == 1


def test_mrb2807_stale_ack_does_not_stop():
    """Stale ACK (past ack_stale_s) must not stop retries even if _ack_job_key matches."""
    tui = _NewlineEnterTui(2)
    clock = [0.0]
    logs: list[str] = []
    b = bw.BoredEmitter(
        lambda: True, lambda m: None, clock=lambda: clock[0], ack_stale_s=10.0
    )
    b.on_outbox("ACK FR SimonBarnett/bobiverse#200")
    assert b.ack_open is True
    clock[0] = 100.0  # past stale window
    assert b.ack_open is False
    assert b.ack_job_ref is None
    line = (
        "FROM Jeeves #marchhare marchhare-1: FR SimonBarnett/bobiverse#200 "
        "https://github.com/SimonBarnett/bobiverse/pull/200"
    )
    ok = bw.inject_with_submit_verify(
        1,
        line,
        inject_fn=tui.inject,
        enter_fn=tui.enter,
        probe_fn=lambda: bool(tui.submitted),
        clock=lambda: clock[0],
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        log=logs.append,
        verify_s=3.0,
        max_retries=3,
        backoffs=(3.0, 5.0, 8.0),
        stop_fn=_stop_for_line(b, line),
        sync=True,
    )
    assert ok is True
    assert any("submit-verify retry=" in m for m in logs)
    assert not any("(stop/ACK)" in m for m in logs)


def test_mrb2807_vision_s3_cites_2791_job_match():
    vision = Path(__file__).resolve().parents[1] / "VISION.md"
    text = vision.read_text(encoding="utf-8")
    # Contiguous S3 row must mention job-matched stop + FR #2791.
    idx = text.index("| S3 |")
    row = text[idx : idx + 900]
    assert "2791" in row
    assert "assign_job_ref" in row or "ack_job_ref" in row
    assert "test_fr2791_submit_verify_stop_matches_job.py" in row
    assert "unrelated open ACK" in row


def test_mrb2807_skill_submit_verify_no_orphan_splice():
    skill = (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-bob-worker"
        / "SKILL.md"
    )
    raw = skill.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    idx = text.index("**Submit verify (FR #2696")
    # Start of bullet through next bullet start must stay one contiguous item.
    nxt = text.find("\n* **", idx + 1)
    chunk = text[idx:nxt] if nxt > 0 else text[idx : idx + 900]
    assert "2791" in chunk
    assert "never re-paste" in chunk
    assert "injected" in chunk.lower() or "assign_job_ref" in chunk
    # No dangling orphan line that is only a clause without a bullet lead-in.
    for line in chunk.splitlines()[1:]:
        if line.startswith("* **"):
            break
        if line.strip() and not line.startswith(" ") and not line.startswith("*"):
            # Continuation of the same bullet paragraph is fine; bare orphan FAIL.
            assert False, f"orphan line in Submit verify bullet: {line!r}"

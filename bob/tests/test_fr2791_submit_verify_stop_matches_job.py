"""FR #2791: submit-verify stop_fn matches the injected job ACK, not any open ACK."""
from __future__ import annotations

import bob_worker as bw


class _NewlineEnterTui:
    """Warm TUI: first N Enter events become newlines; later Enter submits (FR #2782 pattern)."""

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
    """Mirror Supervisor._inject_line stop_fn construction (FR #2791)."""
    want = bw.assign_job_ref(line)
    if not want:
        return None
    return lambda b=bored, w=want: bool(b.ack_open) and (b.ack_job_ref == w)


def test_assign_job_ref_parses_from_and_bare():
    assert (
        bw.assign_job_ref(
            "FROM Jeeves #marchhare marchhare-1: MRB SimonBarnett/bobiverse#200 https://x/y"
        )
        == "simonbarnett/bobiverse#200"
    )
    assert bw.assign_job_ref("FR Other/Repo#7") == "other/repo#7"
    assert bw.assign_job_ref("hello nothing queued") is None
    assert bw.assign_job_ref("FROM Jeeves #m nick: ping") is None


def test_ack_job_ref_from_open_ack():
    clock = [1000.0]
    b = bw.BoredEmitter(lambda: True, lambda m: None, clock=lambda: clock[0])
    assert b.ack_job_ref is None
    b.on_outbox("ACK FR SimonBarnett/bobiverse#100")
    assert b.ack_open is True
    assert b.ack_job_ref == "simonbarnett/bobiverse#100"
    b.on_outbox("DONE FR SimonBarnett/bobiverse#100 https://github.com/SimonBarnett/bobiverse/pull/1")
    assert b.ack_open is False
    assert b.ack_job_ref is None


def test_unrelated_open_ack_does_not_stop_retry():
    """Fails on main before FR #2791: any ack_open returns stop at 0.0s with zero retries."""
    tui = _NewlineEnterTui(2)
    clock = [0.0]
    logs: list[str] = []
    b = bw.BoredEmitter(lambda: True, lambda m: None, clock=lambda: clock[0])
    b.on_outbox("ACK FR SimonBarnett/bobiverse#100")
    assert b.ack_open is True
    line = (
        "FROM Jeeves #marchhare marchhare-1: MRB SimonBarnett/bobiverse#200 "
        "https://github.com/SimonBarnett/bobiverse/pull/200"
    )
    stop = _stop_for_line(b, line)
    assert stop is not None
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
        stop_fn=stop,
        sync=True,
    )
    assert ok is True
    assert len(tui.pastes) == 1
    assert len(tui.submitted) == 1
    assert any("submit-verify retry=" in m for m in logs)
    assert not any("(stop/ACK)" in m for m in logs)
    assert any("submit-verify ok" in m and "(stop/ACK)" not in m for m in logs)


def test_matching_ack_still_stops():
    tui = _NewlineEnterTui(2)
    clock = [0.0]
    logs: list[str] = []
    b = bw.BoredEmitter(lambda: True, lambda m: None, clock=lambda: clock[0])
    line = (
        "FROM Jeeves #marchhare marchhare-1: MRB SimonBarnett/bobiverse#200 "
        "https://github.com/SimonBarnett/bobiverse/pull/200"
    )
    stop = _stop_for_line(b, line)

    # During verify, a matching ACK arrives (case-insensitive repo).
    def sleep_and_ack(s: float) -> None:
        clock[0] += s
        if clock[0] >= 1.0 and not b.ack_open:
            b.on_outbox("ACK mrb SIMONBARNETT/bobiverse#200")

    ok = bw.inject_with_submit_verify(
        1,
        line,
        inject_fn=tui.inject,
        enter_fn=tui.enter,
        probe_fn=lambda: bool(tui.submitted),
        clock=lambda: clock[0],
        sleep=sleep_and_ack,
        log=logs.append,
        verify_s=3.0,
        max_retries=3,
        backoffs=(3.0, 5.0, 8.0),
        stop_fn=stop,
        sync=True,
    )
    assert ok is True
    assert len(tui.pastes) == 1
    assert any("(stop/ACK)" in m for m in logs)


def test_same_number_other_repo_does_not_stop():
    tui = _NewlineEnterTui(2)
    clock = [0.0]
    logs: list[str] = []
    b = bw.BoredEmitter(lambda: True, lambda m: None, clock=lambda: clock[0])
    b.on_outbox("ACK MRB SimonBarnett/other#200")
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
    assert len(tui.submitted) == 1
    assert any("submit-verify retry=" in m for m in logs)
    assert not any("(stop/ACK)" in m for m in logs)


def test_non_assign_inject_has_no_stop_fn():
    line = "FROM Jeeves #marchhare marchhare-1: hello there"
    assert bw.assign_job_ref(line) is None
    b = bw.BoredEmitter(lambda: True, lambda m: None, clock=lambda: 0.0)
    b.on_outbox("ACK FR SimonBarnett/bobiverse#1")
    assert _stop_for_line(b, line) is None


def test_no_repaste_in_unrelated_ack_case():
    tui = _NewlineEnterTui(2)
    clock = [0.0]
    b = bw.BoredEmitter(lambda: True, lambda m: None, clock=lambda: clock[0])
    b.on_outbox("ACK FR SimonBarnett/bobiverse#100")
    line = "FROM Jeeves #m n: FR SimonBarnett/bobiverse#200 https://x"
    inject_calls = []

    def inject_once(pid, text, submit_gap_s=None):
        inject_calls.append(text)
        return tui.inject(pid, text, submit_gap_s)

    bw.inject_with_submit_verify(
        1,
        line,
        inject_fn=inject_once,
        enter_fn=tui.enter,
        probe_fn=lambda: bool(tui.submitted),
        clock=lambda: clock[0],
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        verify_s=3.0,
        max_retries=3,
        backoffs=(3.0, 5.0, 8.0),
        stop_fn=_stop_for_line(b, line),
        sync=True,
    )
    assert len(inject_calls) == 1


def test_inject_line_source_wires_job_matched_stop():
    src = open(bw.__file__, encoding="utf-8").read()
    i = src.index("def _inject_line")
    body = src[i : i + 1600]
    assert "assign_job_ref" in body
    assert "ack_job_ref" in body
    assert "ack_open" in body

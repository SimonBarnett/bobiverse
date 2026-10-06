"""FR #2782: a hotpatched bob-worker build must reach a running seat (stale-build idle recycle).

Live evidence (MarchHare 2026-10-06): seat marchhare-39556 started 12:55:57 from bob-worker-d409556250b4.exe
(pre FR #2696). Hotpatches at 13:52 / 14:23 replaced C:\\ai\\bob\\worker\\bob-worker.exe, but the seat kept its run
copy for 3h, so the warm 15:47:31 assign (MRB #2765) had both Enters taken as newlines and no submit-verify retry.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path

import bob_worker as bw


def _install(tmp_path: Path, payload: bytes = b"new-build", age_s: float = 3600.0) -> tuple[Path, str]:
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    exe = root / "worker" / "bob-worker.exe"
    exe.write_bytes(payload)
    old = time.time() - age_s
    os.utime(exe, (old, old))
    return root, hashlib.sha256(payload).hexdigest()[:12]


def _clean_env() -> dict:
    return {}


def test_stale_when_install_hash_differs(tmp_path):
    root, d = _install(tmp_path)
    why = bw.stale_build_reason(r"C:\x\bob-worker-d409556250b4.exe", root, env=_clean_env())
    assert why == f"run=d409556250b4 install={d}"


def test_not_stale_when_same_build(tmp_path):
    root, d = _install(tmp_path)
    assert bw.stale_build_reason(rf"C:\x\bob-worker-{d}.exe", root, env=_clean_env()) is None
    assert bw.stale_build_reason(rf"C:\x\BOB-WORKER-{d.upper()}.EXE", root, env=_clean_env()) is None


def test_dev_run_or_missing_install_never_stale(tmp_path):
    root, _ = _install(tmp_path)
    assert bw.stale_build_reason(r"C:\Python312\python.exe", root, env=_clean_env()) is None
    assert bw.stale_build_reason(r"C:\ai\bob\worker\bob-worker.exe", root, env=_clean_env()) is None
    assert bw.stale_build_reason(r"C:\x\bob-worker-d409556250b4.exe", tmp_path / "nope", env=_clean_env()) is None


def test_hotpatch_in_flight_waits_for_settle(tmp_path):
    root, _ = _install(tmp_path, age_s=5.0)
    assert bw.stale_build_reason(r"C:\x\bob-worker-d409556250b4.exe", root, env=_clean_env()) is None
    later = time.time() + bw.STALE_BUILD_SETTLE_S + 1
    assert bw.stale_build_reason(r"C:\x\bob-worker-d409556250b4.exe", root, env=_clean_env(), now=later)


def test_opt_out_and_no_seat_heal(tmp_path):
    root, _ = _install(tmp_path)
    run = r"C:\x\bob-worker-d409556250b4.exe"
    assert bw.stale_build_reason(run, root, env={"BOB_WORKER_STALE_BUILD_RECYCLE": "0"}) is None
    # Nobody would refill the seat: never drop below the cap.
    assert bw.stale_build_reason(run, root, env={"BOBIVERSE_WORKER_SEAT_HEAL": "0"}) is None


class _Irc:
    def __init__(self):
        self.alive = True
        self.shop = "#marchhare"
        self.said: list = []
        self.closed: list = []
        self.on_nak = None
        self.on_lost = None
        self.on_message = None

    def say(self, target, text):
        self.said.append((target, text))
        return True

    def close(self, why=""):
        self.closed.append(why)
        self.alive = False


def _sup(tmp_path, irc):
    logs: list = []
    relay = bw.Relay(logs.append, persist_dir=tmp_path)
    sup = bw.Supervisor(kind="grok", exe=r"C:\x\agent.exe", cwd=str(tmp_path), machine="marchhare",
                        nick="marchhare-4242", run_dir=tmp_path, irc=irc, relay=relay, log=logs.append,
                        bored=None)
    return sup, logs


def test_idle_stale_seat_recycles_instead_of_bored(tmp_path):
    """FAILS on main (no stale_build_check): the stale seat posts !bored and takes the next assign on the old build."""
    irc = _Irc()
    sup, logs = _sup(tmp_path, irc)
    sup.stale_build_check = lambda: "run=d409556250b4 install=e5dbd4368d62"
    assert sup.post_bored() is False
    assert ("#marchhare", "!bored") not in irc.said
    assert sup.done.wait(5.0)
    assert sup.exit_code == bw.EXIT_STALE_BUILD == 8
    assert any("stale build (run=d409556250b4 install=e5dbd4368d62)" in m for m in logs)


def test_current_build_still_posts_bored(tmp_path):
    irc = _Irc()
    sup, _ = _sup(tmp_path, irc)
    sup.stale_build_check = lambda: None
    assert sup.post_bored() is True
    assert irc.said == [("#marchhare", "!bored")]
    assert not sup.done.is_set()


def test_stale_check_error_never_blocks_bored(tmp_path):
    irc = _Irc()
    sup, _ = _sup(tmp_path, irc)

    def boom():
        raise OSError("locked")

    sup.stale_build_check = boom
    assert sup.post_bored() is True


def test_busy_seat_never_reaches_the_recycle_point():
    """post_bored (the only recycle point) is never called with an open ACK: recycle can't happen mid-job."""
    sent: list = []
    clock = [1000.0]
    b = bw.BoredEmitter(lambda: sent.append(1) or True, lambda m: None, clock=lambda: clock[0], harvest_hold_s=90.0)
    b.set_ready(True)
    b.on_outbox("ACK MRB SimonBarnett/bobiverse#2765")
    clock[0] += 600
    assert b._reason(clock[0]) is None
    b.on_outbox("DONE MRB SimonBarnett/bobiverse#2765 PASS https://github.com/SimonBarnett/bobiverse/pull/2765")
    clock[0] += 30
    assert b._reason(clock[0]) is None  # harvest hold
    clock[0] += 61
    assert b._reason(clock[0]) in ("start", "done")


class _NewlineEnterTui:
    """Warm grok TUI just after DONE (#2765 evidence): Enter events land in the paste window and become newlines."""

    def __init__(self, newline_enters: int = 2):
        self.newline_left = newline_enters
        self.box = ""
        self.pastes: list = []
        self.submitted: list = []

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


def test_warm_after_done_newline_enters_submit_on_retry():
    """Pins the warm/just-after-DONE case on the FR #2696 build (passes on main; the 39556 miss was the stale exe)."""
    tui = _NewlineEnterTui(2)
    b = bw.BoredEmitter(lambda: True, lambda m: None, clock=lambda: 0.0)
    b.on_outbox("ACK MRB SimonBarnett/bobiverse#2763")
    b.on_outbox("DONE MRB SimonBarnett/bobiverse#2763 PASS https://github.com/SimonBarnett/bobiverse/pull/2763")
    t = [0.0]
    logs: list = []
    ok = bw.inject_with_submit_verify(
        1, "FROM Jeeves #marchhare marchhare-39556: MRB SimonBarnett/bobiverse#2765 x",
        inject_fn=tui.inject, enter_fn=tui.enter, probe_fn=lambda: bool(tui.submitted),
        clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s), log=logs.append,
        verify_s=3.0, max_retries=3, backoffs=(3.0, 5.0, 8.0),
        stop_fn=lambda: bool(b.ack_open), sync=True,
    )
    assert ok is True
    assert len(tui.pastes) == 1
    assert len(tui.submitted) == 1
    assert any("submit-verify retry=1" in m for m in logs)

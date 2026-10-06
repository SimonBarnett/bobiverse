"""FR #2632: concurrent shells on the same Query queue; both get real DONE (no busy exit=1).

Fallout of #2615 busy fail-closed: two Invoke-AircRemote Commands overlapped and the
second always got ``busy: prior shell still emitting`` + DONE exit=1 with no retry.
"""
from __future__ import annotations

import threading
import time

import airc_console as ac


def test_fr2632_second_shell_queues_then_runs():
    seen: list[str] = []
    lock = threading.Lock()

    def capture(_nick: str, line: str) -> None:
        with lock:
            seen.append(line)

    runner = ac.ShellJobRunner(on_reply=capture, wait=False, timeout_s=30, pending_max=4)

    hold = threading.Event()
    release = threading.Event()

    def blocker() -> None:
        hold.set()
        release.wait(timeout=5)

    # Occupy the Query with a fake in-flight thread, then enqueue a real command.
    t = threading.Thread(target=blocker, name="airc-shell-bob-tm", daemon=True)
    with runner._lock:
        runner._threads["bob-tm"] = t
    t.start()
    assert hold.wait(timeout=2)

    runner.start("bob-tm", "id=aabbccdd Write-Output queued-ok")
    with lock:
        assert not any("busy" in x.lower() for x in seen)
        assert not any(x.startswith("DONE id=aabbccdd") for x in seen)
    pending = list(runner._pending.get("bob-tm") or ())
    assert any(p.command.startswith("id=aabbccdd") for p in pending), pending

    # Finish the fake prior; drain must pick up the queued command.
    # Replace fake thread bookkeeping so _drain can own the slot: clear and start drain
    # by calling start again after releasing — instead release fake and manually drain.
    release.set()
    t.join(timeout=2)
    with runner._lock:
        runner._threads.pop("bob-tm", None)
        # Pending still has the command; kick a drain thread.
        if runner._pending.get("bob-tm"):
            d = threading.Thread(
                target=runner._drain, args=("bob-tm",), name="airc-shell-bob-tm", daemon=True
            )
            runner._threads["bob-tm"] = d
            d.start()

    deadline = time.time() + 15
    while time.time() < deadline:
        with lock:
            if any(x == "DONE id=aabbccdd exit=0" for x in seen):
                break
        time.sleep(0.05)
    with lock:
        assert any(x.startswith("out id=aabbccdd") and "queued-ok" in x for x in seen), seen
        assert any(x == "DONE id=aabbccdd exit=0" for x in seen), seen
        assert not any("busy" in x.lower() for x in seen)


def test_fr2632_two_real_shells_both_done():
    """Back-to-back starts: both commands run and emit their own DONE."""
    seen: list[str] = []
    lock = threading.Lock()

    def capture(_nick: str, line: str) -> None:
        with lock:
            seen.append(line)

    runner = ac.ShellJobRunner(on_reply=capture, wait=False, timeout_s=30)
    runner.start(
        "bob-tm",
        'id=11111111 Write-Output "A1"; Start-Sleep -Milliseconds 400; Write-Output "A-done"',
    )
    runner.start(
        "bob-tm",
        'id=22222222 Write-Output "B1"; Start-Sleep -Milliseconds 200; Write-Output "B-done"',
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        with lock:
            have_a = any(x == "DONE id=11111111 exit=0" for x in seen)
            have_b = any(x == "DONE id=22222222 exit=0" for x in seen)
            if have_a and have_b:
                break
        time.sleep(0.05)

    with lock:
        assert any(x == "DONE id=11111111 exit=0" for x in seen), seen
        assert any(x == "DONE id=22222222 exit=0" for x in seen), seen
        assert not any("busy" in x.lower() for x in seen), seen
        # Order: A finishes before B starts emitting (serial per Query).
        a_done_i = next(i for i, x in enumerate(seen) if x == "DONE id=11111111 exit=0")
        b_out_i = next(i for i, x in enumerate(seen) if x.startswith("out id=22222222"))
        assert a_done_i < b_out_i


def test_fr2632_queue_overflow_still_busy_done():
    seen: list[str] = []

    def capture(_nick: str, line: str) -> None:
        seen.append(line)

    runner = ac.ShellJobRunner(on_reply=capture, wait=False, pending_max=1)
    hold = threading.Event()
    release = threading.Event()

    def blocker() -> None:
        hold.set()
        release.wait(timeout=5)

    t = threading.Thread(target=blocker, name="airc-shell-bob-tm", daemon=True)
    with runner._lock:
        runner._threads["bob-tm"] = t
    t.start()
    assert hold.wait(timeout=2)
    try:
        runner.start("bob-tm", "id=aaaaaaa1 Write-Output keep")
        runner.start("bob-tm", "id=bbbbbbb2 Write-Output overflow")
        assert any(x.startswith("err id=bbbbbbb2") and "busy" in x.lower() for x in seen)
        assert any(x == "DONE id=bbbbbbb2 exit=1" for x in seen)
        # First overflow victim only; queued id must not have busy.
        assert not any(x.startswith("err id=aaaaaaa1") and "busy" in x.lower() for x in seen)
    finally:
        release.set()
        t.join(timeout=2)
        with runner._lock:
            runner._pending.pop("bob-tm", None)
            runner._threads.pop("bob-tm", None)

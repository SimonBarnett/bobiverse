"""FR #2556: recycle/cap must kill onefile seat roots, never flat PID Skip-N."""
from __future__ import annotations

import bob_worker as bw


def _pair(root: int, child: int, name: str = "bob-worker.exe"):
    # bootloader root (parent not a worker), child parent=root
    return [(root, 1, name), (child, root, name)]


def test_worker_seat_roots_onefile_pair_is_one_seat():
    procs = _pair(100, 101) + _pair(200, 201)
    assert bw.worker_seat_roots(procs) == [100, 200]


def test_worker_seat_tree_pids_includes_bootloader_and_child():
    procs = _pair(100, 101) + _pair(200, 201)
    assert bw.worker_seat_tree_pids(procs, 100) == [100, 101]
    assert bw.worker_seat_tree_pids(procs, 200) == [200, 201]
    assert 101 not in bw.worker_seat_roots(procs)  # expand trees from roots only


def test_excess_worker_seat_roots_keeps_newest_pair():
    """Two onefile seats (4 procs). keep=1 must return the older ROOT only — not a flat Skip-2 PID list."""
    procs = _pair(100, 101) + _pair(200, 201)
    # Naive Skip-2 by sorted PID would yield kill list [200,201] or [100,101] mixed wrong;
    # correct excess is older root [100] (tree 100+101), keeping seat 200+201.
    assert bw.excess_worker_seat_roots(procs, keep=1) == [100]
    kill = []
    for root in bw.excess_worker_seat_roots(procs, keep=1):
        kill.extend(bw.worker_seat_tree_pids(procs, root))
    assert sorted(kill) == [100, 101]
    # Flat Skip-2 on all worker pids is the bug that killed MarchHare's second seat.
    flat = sorted(p for p, _pp, n in procs if bw._WORKER_EXE_RX.match(n))
    naive = flat[2:]  # Skip-2 keep first two PIDs
    assert naive == [200, 201]  # would kill the NEW seat's tree — wrong
    assert sorted(kill) != sorted(naive)


def test_excess_keep_two_with_two_seats_empty():
    procs = _pair(100, 101) + _pair(200, 201)
    assert bw.excess_worker_seat_roots(procs, keep=2) == []


def test_fr2556_cap_still_seat_aware_with_onefile():
    procs = _pair(100, 101) + _pair(200, 201)
    # Starting a third seat: two other roots already
    assert bw.other_live_workers(procs, 300) == 2
    assert bw.worker_cap_refusal(procs, 300) != ""


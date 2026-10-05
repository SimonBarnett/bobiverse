"""MRB #2557 hostile: FR #2556 seat-root recycle helpers + source markers."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def _hashed_pair(root: int, child: int, digest: str = "5f576af4ad5e"):
    name = f"bob-worker-{digest}.exe"
    return [(root, 1, name), (child, root, name)]


def test_mrb2557_hashed_onefile_pair_is_one_seat():
    procs = _hashed_pair(38244, 40460) + _hashed_pair(32104, 21524)
    assert bw.worker_seat_roots(procs) == [32104, 38244]
    assert bw.excess_worker_seat_roots(procs, keep=1) == [32104]
    kill = []
    for root in bw.excess_worker_seat_roots(procs, keep=1):
        kill.extend(bw.worker_seat_tree_pids(procs, root))
    assert sorted(kill) == [21524, 32104]
    flat = sorted(p for p, _pp, n in procs if bw._WORKER_EXE_RX.match(n))
    naive = flat[2:]
    assert sorted(kill) != sorted(naive)


def test_mrb2557_product_test_utf8_no_bom_no_c0():
    root = Path(__file__).resolve().parents[1]
    path = root / "tests" / "test_fr2556_seat_root_recycle.py"
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert not any(b < 32 and b not in (9, 10, 13) for b in raw)
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_mrb2557_tray_stop_seat_trees_forbids_flat_skip():
    root = Path(__file__).resolve().parents[1]
    ps1 = root / "tray" / "tools" / "BobTrayStartWorker.ps1"
    text = ps1.read_text(encoding="utf-8")
    assert "function Stop-BobWorkerSeatTrees" in text
    assert "FR #2556" in text
    assert "Select -Skip N | Stop-Process" in text
    # Helper body must stop by root/parent link, not Sort ProcessId Skip
    start = text.index("function Stop-BobWorkerSeatTrees")
    body = text[start : start + 450]
    assert "ParentProcessId -eq $root" in body
    assert "Sort-Object ProcessId" not in body


def test_mrb2557_skill_documents_seat_root_recycle_no_c0():
    root = Path(__file__).resolve().parents[1]
    skill = root / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    raw = skill.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\x08" not in raw
    text = raw.decode("utf-8")
    assert "FR #2556" in text
    assert "worker_seat_roots" in text
    assert "Stop-BobWorkerSeatTrees" in text
    assert "bob-worker.exe" in text
    assert "Select -Skip N | Stop-Process" in text

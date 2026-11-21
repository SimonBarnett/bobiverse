"""FR #8597: machine recycle must stop bob-worker seat trees (incl. OpenCode) before restart.

!recycle announced stop_managed_workers but execute_local_recycle only restarted
watch + tray, leaving hung OpenCode seats on the same PIDs.
"""
from __future__ import annotations

from pathlib import Path

import bob_recycle


def test_fr8597_plan_lists_stop_managed_workers_first():
    plan = bob_recycle.build_recycle_plan("flamingo", ionos_chair=False)
    assert plan.steps[0] == "stop_managed_workers"
    assert "recycle_watch_bobtray" in plan.steps


def test_fr8597_execute_calls_stop_before_watch_and_tray(tmp_path, monkeypatch):
    events: list[str] = []

    def stop(_root: Path) -> None:
        events.append("stop")

    def watch(_root: Path, _mid: str) -> None:
        events.append("watch")

    def tray(_root: Path) -> None:
        events.append("tray")

    def pull(_root: Path) -> None:
        events.append("pull")

    monkeypatch.setattr(bob_recycle, "find_install_root", lambda: tmp_path)
    monkeypatch.setattr(bob_recycle, "find_agentic_build_root", lambda: tmp_path)
    monkeypatch.setattr(bob_recycle, "resolve_recycle_machine", lambda mid: mid)

    hooks = bob_recycle.RecycleHooks(
        stop_managed_workers=stop,
        git_pull=pull,
        restart_watch=watch,
        recycle_tray=tray,
    )
    bob_recycle.execute_local_recycle("flamingo", tmp_path, hooks=hooks)
    assert events[:4] == ["stop", "pull", "watch", "tray"]


def test_fr8597_seat_roots_skip_onefile_child():
    # bootloader 100 -> child 101; bootloader 200 -> child 201
    rows = [
        (100, 1, "bob-worker.exe"),
        (101, 100, "bob-worker.exe"),
        (200, 1, "bob-worker-abc.exe"),
        (201, 200, "bob-worker-abc.exe"),
    ]
    assert bob_recycle.bob_worker_seat_roots_from_rows(rows) == [100, 200]


def test_fr8597_stop_targets_roots_with_tree_kill():
    """OpenCode is a grandchild; kill must be invoked on the seat root (taskkill /T)."""
    rows = [
        (100, 1, "bob-worker.exe"),
        (101, 100, "bob-worker.exe"),
        # OpenCode under the onefile child — not a bob-worker name
        (102, 101, "opencode.exe"),
        (200, 1, "bob-worker.exe"),
        (201, 200, "bob-worker.exe"),
    ]
    killed: list[int] = []

    def kill(pid: int) -> None:
        killed.append(pid)

    roots = bob_recycle.stop_managed_worker_seat_trees(rows=rows, kill_fn=kill)
    assert roots == [100, 200]
    assert killed == [100, 200]
    assert 102 not in killed  # grandchild dies via /T on root, not as its own root


def test_fr8597_stop_bob_worker_seat_trees_uses_taskkill_t():
    """Tray helper must tree-kill so OpenCode grandchildren die with the seat."""
    text = (
        Path(__file__).resolve().parents[2]
        / "bob"
        / "tray"
        / "tools"
        / "BobTrayStartWorker.ps1"
    ).read_text(encoding="utf-8")
    start = text.index("function Stop-BobWorkerSeatTrees")
    chunk = text[start : start + 500]
    assert "taskkill" in chunk.lower()
    assert "/T" in chunk or '/T' in chunk

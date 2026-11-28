"""FR #10360: job-worktree git verify must not block the IRC socket read thread."""
from __future__ import annotations

import inspect
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_seat_contract as c  # noqa: E402


def test_deliver_parks_git_prep_before_slow_verify_finishes(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    line_text = "m-1: FR SimonBarnett/bobiverse#10360 https://x"
    from_line = bw.format_from("jeeves", "#redqueen", line_text)
    path = Path(c.project_dir_for_assign(from_line, env))
    path.mkdir(parents=True)
    written: list[str] = []
    injected: list[str] = []
    gate = threading.Event()
    started = threading.Event()

    def verify(line: str) -> None:
        started.set()
        gate.wait(timeout=5.0)

    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = lambda line: c.opencode_job_context_nack(line, env)
    relay.opencode_verify_job_worktree = verify

    t0 = time.monotonic()
    status = relay.deliver("jeeves", "#redqueen", line_text)
    elapsed = time.monotonic() - t0
    assert status == "opencode_worktree_git_pending"
    assert elapsed < 0.5, f"deliver blocked for {elapsed:.3f}s on read path"
    assert not any(item.startswith("ACK ") for item in written)
    assert injected == []
    assert started.wait(timeout=2.0)

    gate.set()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not any(
        item.startswith("ACK FR SimonBarnett/bobiverse#10360") for item in written
    ):
        time.sleep(0.05)
    assert any(item.startswith("ACK FR SimonBarnett/bobiverse#10360") for item in written)
    assert injected


def test_has_pending_work_true_while_git_prep():
    relay = bw.Relay(log=lambda *_a, **_k: None)
    with relay._lock:
        relay._worktree_git_prep_keys.add("fr simonbarnett/bobiverse#10360")
    assert relay.has_pending_work() is True
    with relay._lock:
        relay._worktree_git_prep_keys.clear()
    assert relay.has_pending_work() is False


def test_inject_line_opencode_ready_does_not_sync_verify():
    src = inspect.getsource(bw.Supervisor._inject_line)
    opencode_idx = src.index("opencode-ready: job worktree")
    tail = src[opencode_idx : opencode_idx + 1200]
    assert "verify_job_worktree_git" not in tail


def test_supervisor_binds_git_verify_callback():
    relay = bw.Relay(log=lambda *_a, **_k: None)
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.install_root = r"C:\ai\bob"
    sup.nick = "redqueen-1"
    sup.log = lambda *_a, **_k: None
    if (sup.kind or "").strip().lower() == "opencode":
        relay.opencode_job_classify = sup._opencode_job_classify
        relay.opencode_ensure_worktree = sup._opencode_ensure_worktree
        relay.opencode_verify_job_worktree = sup._opencode_verify_job_worktree_git
    assert relay.opencode_verify_job_worktree is not None
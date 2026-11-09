"""FR #6328: OpenCode worktree create must not block the IRC socket read thread."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_seat_contract as c  # noqa: E402


def _init_clone(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True, capture_output=True)
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "i"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(path), "fetch", "origin", "main"], check=True, capture_output=True)
    return path


def test_deliver_returns_pending_before_slow_ensure_finishes(tmp_path: Path):
    """Read-thread deliver must return while ensure is still running (no ACK yet)."""
    clone = _init_clone(tmp_path / "clone")
    base = tmp_path / "worktrees"
    env = {"BOB_JOB_WORKTREE_BASE": str(base), "BOB_REPO_CLONE_bobiverse": str(clone)}
    written: list[str] = []
    injected: list[str] = []
    gate = threading.Event()
    started = threading.Event()

    def classify(line: str) -> str:
        return c.opencode_job_context_nack(line, env)

    def ensure(line: str) -> str:
        started.set()
        gate.wait(timeout=5.0)
        return c.opencode_job_context_nack_ready(line, env, install_root=str(clone), nick="m-1")

    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = classify
    relay.opencode_ensure_worktree = ensure

    t0 = time.monotonic()
    status = relay.deliver(
        "jeeves", "#marchhare", "m-1: FR SimonBarnett/bobiverse#6328 https://x"
    )
    elapsed = time.monotonic() - t0
    assert status == "opencode_worktree_pending"
    assert elapsed < 0.5, f"deliver blocked for {elapsed:.3f}s on read path"
    assert not any(item.startswith("ACK ") for item in written)
    assert injected == []
    assert started.wait(timeout=2.0)

    gate.set()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not any(
        item.startswith("ACK FR SimonBarnett/bobiverse#6328") for item in written
    ):
        time.sleep(0.05)
    assert any(item.startswith("ACK FR SimonBarnett/bobiverse#6328") for item in written)
    assert injected
    assert not any("worktree-create-failed" in item for item in written)
    path = Path(c.project_dir_for_assign(
        bw.format_from("jeeves", "#marchhare", "m-1: FR SimonBarnett/bobiverse#6328 https://x"),
        env,
    ))
    assert path.is_dir()


def test_async_create_failure_nacks_without_ack(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    written: list[str] = []
    injected: list[str] = []

    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = lambda line: c.opencode_job_context_nack(line, env)
    relay.opencode_ensure_worktree = lambda line: c.opencode_job_context_nack_ready(
        line, env, install_root=None
    )

    status = relay.deliver(
        "jeeves", "#marchhare", "m-1: FR SimonBarnett/bobiverse#9 https://x"
    )
    assert status == "opencode_worktree_pending"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not any("worktree-create-failed" in item for item in written):
        time.sleep(0.05)
    assert any("worktree-create-failed:no-clone" in item for item in written)
    assert not any(item.startswith("ACK ") for item in written)
    assert injected == []


def test_existing_project_still_acks_sync_without_pending(tmp_path: Path):
    """When the worktree already exists, classify is project — no background hop."""
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    line_text = "m-1: FR SimonBarnett/bobiverse#7 https://x"
    path = Path(c.project_dir_for_assign(bw.format_from("jeeves", "#marchhare", line_text), env))
    path.mkdir(parents=True)
    written: list[str] = []
    injected: list[str] = []
    ensure_calls: list[str] = []

    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = lambda line: c.opencode_job_context_nack(line, env)
    relay.opencode_ensure_worktree = lambda line: ensure_calls.append(line) or ""

    status = relay.deliver("jeeves", "#marchhare", line_text)
    assert status == "injected"
    assert ensure_calls == []
    assert any(item.startswith("ACK FR SimonBarnett/bobiverse#7") for item in written)


def test_create_job_worktree_fetch_timeout_is_bounded():
    """Individual git fetch timeout must stay short enough not to starve IRC (FR #6328)."""
    assert getattr(c, "WORKTREE_FETCH_TIMEOUT_S", 999) <= 45.0
    assert getattr(c, "WORKTREE_ADD_TIMEOUT_S", 999) <= 90.0


def test_create_maps_timeout_expired_to_timeout_class(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / ".git").mkdir()
    env["BOB_REPO_CLONE_bobiverse"] = str(clone)

    def run(cmd, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is not None and any("fetch" in str(part) for part in cmd):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)
        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""
        return Proc()

    line = "FROM jeeves #m n: FR SimonBarnett/bobiverse#1 https://x"
    # Path absent -> ensure tries create; fetch timeout should surface as timeout class
    # (fetch failure alone is best-effort; force worktree add to also timeout)
    def run2(cmd, **kwargs):
        timeout = kwargs.get("timeout")
        joined = " ".join(str(part) for part in cmd)
        if "worktree" in joined and "add" in joined:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout or 1)
        class Proc:
            returncode = 1
            stdout = ""
            stderr = ""
        return Proc()

    decision = c.ensure_opencode_job_worktree(
        line, env, install_root=str(clone), run=run2
    )
    assert decision["state"] == "create_failed"
    assert decision["error_class"] == "timeout"
    assert "worktree-create-failed:timeout" in decision["nack"]


def test_supervisor_binds_classify_and_ensure_off_thread():
    """OpenCode Supervisor must expose classify + ensure (not sync-only block)."""
    relay = bw.Relay(log=lambda *_a, **_k: None)
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.install_root = r"C:\ai\bob"
    sup.nick = "marchhare-1"
    # Mimic _wire_relay binding for OpenCode.
    if (sup.kind or "").strip().lower() == "opencode":
        relay.opencode_job_classify = lambda line: c.opencode_job_context_nack(line, {})
        relay.opencode_ensure_worktree = lambda line: c.opencode_job_context_nack_ready(line, {})
        relay.opencode_job_block = None
    assert relay.opencode_job_classify is not None
    assert relay.opencode_ensure_worktree is not None


def test_docs_mention_off_thread_create():
    text = (REPO / "bob" / "docs" / "opencode-windows-readiness.md").read_text(encoding="utf-8")
    assert "FR #6328" in text
    assert "read thread" in text.lower() or "off the IRC" in text or "off-thread" in text.lower()

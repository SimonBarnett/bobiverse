# -*- coding: utf-8 -*-
"""FR #9228: after parked worktree ensure ok, always ACK+inject (no silent resume drop)."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import bob_worker as bw
import opencode_seat_contract as c


def test_fr9228_resume_logs_and_acks_when_classify_still_absent(tmp_path: Path):
    """Ensure returns ok (empty nack) but classify still absent — must NACK verify, not re-park."""
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    written: list[str] = []
    injected: list[str] = []
    logs: list[str] = []

    relay = bw.Relay(log=logs.append, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = lambda line: c.opencode_job_context_nack(line, env)
    # Ensure "succeeds" without creating the tree (simulates path skew / silent ok).
    relay.opencode_ensure_worktree = lambda line: ""

    status = relay.deliver(
        "jeeves", "#redqueen", "redqueen-1: FIX SimonBarnett/bobiverse#9125 https://x"
    )
    assert status == "opencode_worktree_pending"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not any(
        "worktree-create-failed:verify" in item for item in written
    ):
        time.sleep(0.05)
    assert any("worktree-create-failed:verify" in item for item in written)
    assert not any(item.startswith("ACK ") for item in written)
    assert any("worktree ensure ok" in item for item in logs)
    assert any("resume status=" in item for item in logs)


def test_fr9228_resume_acks_after_ensure_creates(tmp_path: Path):
    """Happy path: ensure creates tree; resume must ACK+inject and log status."""
    import subprocess

    clone = tmp_path / "clone"
    clone.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(clone)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(clone), "config", "user.email", "t@t"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(clone), "config", "user.name", "t"],
        check=True,
        capture_output=True,
    )
    (clone / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "README"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(clone), "commit", "-m", "i"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(clone), "remote", "add", "origin", str(clone)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(clone), "fetch", "origin", "main"],
        check=True,
        capture_output=True,
    )

    base = tmp_path / "worktrees"
    env = {
        "BOB_JOB_WORKTREE_BASE": str(base),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    written: list[str] = []
    injected: list[str] = []
    logs: list[str] = []
    gate = threading.Event()

    def ensure(line: str) -> str:
        gate.wait(timeout=5.0)
        return c.opencode_job_context_nack_ready(
            line, env, install_root=str(clone), nick="redqueen-1"
        )

    relay = bw.Relay(log=logs.append, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = lambda line: c.opencode_job_context_nack(line, env)
    relay.opencode_ensure_worktree = ensure

    # FR assigns create from origin/main (no gh pr head).
    status = relay.deliver(
        "jeeves", "#redqueen", "redqueen-1: FR SimonBarnett/bobiverse#9228 https://x"
    )
    assert status == "opencode_worktree_pending"
    gate.set()
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and not any(
        item.startswith("ACK FR SimonBarnett/bobiverse#9228") for item in written
    ):
        time.sleep(0.05)
    assert any(item.startswith("ACK FR SimonBarnett/bobiverse#9228") for item in written)
    assert injected
    assert any("worktree ensure ok" in item for item in logs)
    assert any("worktree create resume status=" in item for item in logs)


def test_fr9228_force_resume_after_duplicate(tmp_path: Path):
    """If deliver resume soft-returns duplicate, force path still ACK/injects."""
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    path = Path(
        c.project_dir_for_assign(
            bw.format_from(
                "jeeves",
                "#redqueen",
                "redqueen-1: FR SimonBarnett/bobiverse#7 https://x",
            ),
            env,
        )
    )
    path.mkdir(parents=True)
    written: list[str] = []
    injected: list[str] = []
    logs: list[str] = []

    relay = bw.Relay(log=logs.append, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_classify = lambda line: c.opencode_job_context_nack(line, env)
    relay.opencode_ensure_worktree = lambda line: ""

    # Pretend a prior deliver already remembered this line (silent duplicate trap).
    line = bw.format_from(
        "jeeves",
        "#redqueen",
        "redqueen-1: FR SimonBarnett/bobiverse#7 https://x",
        outbox=relay.outbox_path,
    )
    with relay._lock:
        relay._last_line = line

    status = relay.deliver(
        "jeeves",
        "#redqueen",
        "redqueen-1: FR SimonBarnett/bobiverse#7 https://x",
        resume_after_worktree=True,
    )
    assert status == "injected"
    assert any(item.startswith("ACK FR SimonBarnett/bobiverse#7") for item in written)
    assert injected


def test_fr9228_stale_offer_log(tmp_path: Path):
    logs: list[str] = []
    now = [1000.0]
    relay = bw.Relay(
        log=logs.append,
        outbox_path=tmp_path / "outbox.txt",
        clock=lambda: now[0],
    )
    with relay._lock:
        relay._worktree_parked_at["fix simonbarnett/bobiverse#9125"] = 1000.0
        relay._worktree_creating_keys.add("fix simonbarnett/bobiverse#9125")
    now[0] = 1000.0 + 200.0
    relay.maybe_log_stale_worktree_offer(min_age_s=180.0)
    assert any("stale worktree offer" in item for item in logs)
    # Once only.
    logs.clear()
    relay.maybe_log_stale_worktree_offer(min_age_s=180.0)
    assert not any("stale worktree offer" in item for item in logs)


def test_fr9228_source_pins():
    text = Path(bw.__file__).read_text(encoding="utf-8")
    assert "resume_after_worktree" in text
    assert "_force_ack_inject_after_worktree" in text
    assert "maybe_log_stale_worktree_offer" in text
    assert "worktree ensure ok" in text
    assert "FR #9228" in text

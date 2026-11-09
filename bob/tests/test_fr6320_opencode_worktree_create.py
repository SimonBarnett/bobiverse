"""FR #6320: OpenCode worker creates job worktree before ACK."""
from __future__ import annotations

import subprocess
import sys
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
    # origin/main for worktree add
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(path), "fetch", "origin", "main"], check=True, capture_output=True)
    return path


def test_ensure_creates_worktree_then_project(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    base = tmp_path / "worktrees"
    env = {"BOB_JOB_WORKTREE_BASE": str(base), "BOB_REPO_CLONE_bobiverse": str(clone)}
    line = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#6320 https://x"
    before = c.classify_opencode_job(line, env)
    assert before["state"] == "absent"
    ready = c.ensure_opencode_job_worktree(line, env, install_root=str(clone))
    assert ready["state"] == "project"
    assert ready["nack"] == ""
    path = Path(ready["path"])
    assert path.is_dir()
    assert (path / ".git").exists() or (path / ".git").is_file()
    # Idempotent reuse
    again = c.ensure_opencode_job_worktree(line, env, install_root=str(clone))
    assert again["state"] == "project"
    assert Path(again["path"]) == path
    args = c.opencode_run_args("opencode/beam-free", "hello", ready["path"])
    assert args[:3] == ["run", "--dir", str(path.resolve())]
    assert "--auto" not in args


def test_ensure_reuses_existing_directory_without_git(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    line = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#7 https://x"
    path = Path(c.project_dir_for_assign(line, env))
    path.mkdir(parents=True)
    calls: list[list[str]] = []

    def run(cmd, **_k):
        calls.append(list(cmd))

        class Proc:
            returncode = 1
            stdout = ""
            stderr = "should not run"

        return Proc()

    ready = c.ensure_opencode_job_worktree(line, env, run=run)
    assert ready["state"] == "project"
    assert calls == []


def test_create_failure_nacks_specific_reason_no_ack(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    # No clone configured -> no-clone
    line = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#99 https://x"
    decision = c.ensure_opencode_job_worktree(line, env, install_root=None)
    assert decision["state"] == "create_failed"
    assert decision["nack"] == (
        "NACK FR SimonBarnett/bobiverse#99 worktree-create-failed:no-clone (FR #6240)"
    )
    assert c.opencode_job_context_nack_ready(line, env) == decision["nack"]
    # classify without ensure still reports absent (legacy)
    assert c.classify_opencode_job(line, env)["state"] == "absent"
    assert "worktree-absent" in c.opencode_job_context_nack(line, env)


def test_credential_path_still_refused(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": r"C:\passwords\worktrees"}
    line = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#1 https://x"
    decision = c.ensure_opencode_job_worktree(line, env)
    assert decision["state"] == "forbidden"
    assert "opencode-dir-forbidden" in decision["nack"]
    assert "worktree-create-failed" not in decision["nack"]


def test_supervisor_block_creates_then_relay_acks(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    base = tmp_path / "worktrees"
    env = {"BOB_JOB_WORKTREE_BASE": str(base), "BOB_REPO_CLONE_bobiverse": str(clone)}
    written: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup.kind = "opencode"
    sup.install_root = str(clone)
    sup.nick = "marchhare-17180"
    # Bind ensure path with test env (not process env).
    relay.opencode_job_block = lambda line: c.opencode_job_context_nack_ready(
        line, env, install_root=str(clone), nick="marchhare-17180"
    )
    text = "marchhare-17180: FR SimonBarnett/bobiverse#6320 https://x"
    status = relay.deliver("jeeves", "#marchhare", text)
    assert status == "injected"
    assert injected
    assert any(item.startswith("ACK FR SimonBarnett/bobiverse#6320") for item in written)
    assert not any("worktree-absent" in item for item in written)
    assert not any("worktree-create-failed" in item for item in written)
    path = Path(c.project_dir_for_assign(bw.format_from("jeeves", "#marchhare", text), env))
    assert path.is_dir()
    # Framing (--dir) is applied in Supervisor._inject_line via prepare_opencode_wire.
    prepared = c.prepare_opencode_wire(
        bw.format_from("jeeves", "#marchhare", text), env
    )
    assert prepared["state"] == "project" and prepared["wire"]
    frame = c.parse_opencode_frame(prepared["wire"])
    assert frame is not None and Path(frame["dir"]).is_dir()
    args = c.opencode_run_args("opencode/beam-free", "hello", frame["dir"])
    assert args[:3] == ["run", "--dir", str(Path(frame["dir"]).resolve())]
    assert "--auto" not in args


def test_supervisor_create_fail_nacks_without_ack(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    written: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.opencode_job_block = lambda line: c.opencode_job_context_nack_ready(
        line, env, install_root=None
    )
    status = relay.deliver(
        "jeeves", "#marchhare", "marchhare-1: FR SimonBarnett/bobiverse#3 https://x"
    )
    assert status == "opencode_job_blocked"
    assert injected == []
    assert any("worktree-create-failed:no-clone" in item for item in written)
    assert not any(item.startswith("ACK ") for item in written)


def test_docs_step_two_says_worker_creates():
    text = (REPO / "bob" / "docs" / "opencode-windows-readiness.md").read_text(encoding="utf-8")
    assert "FR #6320" in text
    assert "worker creates" in text.lower() or "creates `Get-BobiverseJobWorktreePath`" in text
    assert "worktree-create-failed" in text
    assert "The worker will not create it" not in text


def test_resolve_repo_clone_bobiverse_install_root(tmp_path: Path):
    clone = _init_clone(tmp_path / "bob")
    assert c.resolve_repo_clone("SimonBarnett/bobiverse", {}, install_root=str(clone)) == str(clone)
    other = _init_clone(tmp_path / "a-search")
    env = {"BOB_AI_ROOT": str(tmp_path)}
    assert c.resolve_repo_clone("SimonBarnett/a-search", env).endswith("a-search")
    assert other.is_dir()

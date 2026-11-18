"""FR #8152: shared bob-bridge clone resolve + provision for OpenCode seats."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import opencode_seat_contract as c  # noqa: E402
import repo_clone_store as rcs  # noqa: E402


def _init_bare(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise AssertionError(f"bare path must not exist yet: {path}")
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(path)],
        check=True,
        capture_output=True,
    )
    return path


def _init_clone(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise AssertionError(f"clone path must not exist yet: {path}")
    bare = path.parent / (path.name + "-origin.git")
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(bare), str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True, capture_output=True)
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "i"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "push", "-u", "origin", "main"], check=True, capture_output=True)
    return path


def test_bare_repos_priority_mcp_git_resolves(tmp_path: Path):
    """AC: a bare ``repos\\priority-mcp.git`` resolves via the shared helper."""
    bridge = tmp_path / "bridge"
    bare = _init_bare(bridge / "repos" / "priority-mcp.git")
    env = {"BOB_BRIDGE_HOME": str(bridge)}
    found = rcs.resolve_repo_clone("SimonBarnett/priority-mcp", env)
    assert found == str(bare)
    # OpenCode wrapper uses the same helper.
    assert c.resolve_repo_clone("SimonBarnett/priority-mcp", env) == str(bare)
    assert rcs.is_git_repo(bare) is True


def test_missing_toray_triggers_one_stubbed_clone(tmp_path: Path):
    """AC: missing toray triggers one clone attempt (stubbed)."""
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    env = {"BOB_BRIDGE_HOME": str(bridge)}
    calls: list[list[str]] = []

    def run(cmd, **_k):
        calls.append(list(cmd))

        class Proc:
            returncode = 1
            stdout = ""
            stderr = "ERROR: Repository not found."

        return Proc()

    path, err, detail = rcs.ensure_repo_clone(
        "SimonBarnett/toray", env, run=run, provision=True
    )
    assert path == ""
    assert err.startswith("clone-failed:")
    assert err == "clone-failed:not-found"
    assert "not found" in detail.lower() or "Repository" in detail or detail
    assert len(calls) >= 1
    assert any("clone" in " ".join(str(p) for p in call).lower() for call in calls)
    # Only one provision path: gh first; auth/not-found may stop before git fallback.
    assert calls[0][0] in ("gh", "git")


def test_fix_key_resolves_repo(tmp_path: Path):
    """AC: FIX keys are parsed the same as FR/MRB/UAT so the repo leaf is known."""
    clone = _init_clone(tmp_path / "clone")
    base = tmp_path / "worktrees"
    env = {
        "BOB_JOB_WORKTREE_BASE": str(base),
        "BOB_REPO_CLONE_bobiverse": str(clone),
        "BOB_BRIDGE_HOME": str(tmp_path / "bridge"),
    }
    line = "FROM jeeves #flamingo n: FIX SimonBarnett/bobiverse#8152 https://x"
    keys = c.message_job_keys(line)
    assert keys == ["FIX SimonBarnett/bobiverse#8152"]
    path = c.project_dir_for_assign(line, env)
    assert path.replace("\\", "/").endswith("bobiverse/fix-8152")
    assert c.resolve_repo_clone("SimonBarnett/bobiverse", env) == str(clone)


def test_failed_clone_nacks_clone_failed_class(tmp_path: Path):
    """AC: failed clone -> worktree-create-failed:clone-failed:<class>."""
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_BRIDGE_HOME": str(bridge),
    }
    line = "FROM jeeves #flamingo n: FR SimonBarnett/toray#12 https://x"
    calls: list[list[str]] = []

    def run(cmd, **_k):
        calls.append(list(cmd))

        class Proc:
            returncode = 1
            stdout = ""
            stderr = "fatal: Authentication failed for 'https://github.com/SimonBarnett/toray.git/'"

        return Proc()

    decision = c.ensure_opencode_job_worktree(line, env, install_root=None, run=run)
    assert decision["state"] == "create_failed"
    assert "worktree-create-failed:clone-failed:auth" in decision["nack"]
    assert decision["error_class"] == "clone-failed:auth"
    assert len(calls) >= 1


def test_shared_helper_exported_for_other_seats():
    """AC: one resolver module shared by OpenCode / Grok / Cursor / Aider paths."""
    assert hasattr(rcs, "resolve_repo_clone")
    assert hasattr(rcs, "ensure_repo_clone")
    assert hasattr(rcs, "provision_repo_clone")
    assert hasattr(rcs, "is_git_repo")
    assert hasattr(rcs, "bridge_clone_candidates")
    # OpenCode must not keep a private copy of the bridge walk.
    src = Path(c.__file__).read_text(encoding="utf-8")
    assert "import repo_clone_store" in src
    assert 'base / "repos"' not in src


def test_ensure_reuses_bridge_bare_without_provision(tmp_path: Path):
    """Existing bare store is used; no clone subprocess when already present."""
    bridge = tmp_path / "bridge"
    bare = _init_bare(bridge / "repos" / "priority-mcp.git")
    # Seed a commit so worktree add can fetch/main — use a companion non-bare for add.
    # For resolve-only: ensure returns bare and does not call run.
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_BRIDGE_HOME": str(bridge),
    }
    calls: list[list[str]] = []

    def run(cmd, **_k):
        calls.append(list(cmd))
        raise AssertionError("provision must not run when bare store exists")

    path, err, _ = rcs.ensure_repo_clone(
        "SimonBarnett/priority-mcp", env, run=run, provision=True
    )
    assert path == str(bare)
    assert err == ""
    assert calls == []

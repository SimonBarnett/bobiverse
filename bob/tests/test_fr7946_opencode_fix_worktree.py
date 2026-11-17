"""FR #7946: OpenCode FIX/MRB worktrees check out the PR head branch."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "fetch", "origin", "main"], check=True, capture_output=True)
    return path


def _publish_head(clone: Path, branch: str) -> None:
    subprocess.run(["git", "-C", str(clone), "checkout", "-b", branch], check=True, capture_output=True)
    (clone / "HEAD.txt").write_text(branch + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "HEAD.txt"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone), "commit", "-m", branch], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone), "checkout", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone), "fetch", "origin", branch], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone), "branch", "-D", branch], check=True, capture_output=True)


def _head_oid(clone: Path, branch: str) -> str:
    return subprocess.run(
        ["git", "-C", str(clone), "rev-parse", f"origin/{branch}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def _run_with_gh(head: str | None, oid: str | None = None, *, gh_code: int = 0):
    def run(cmd, **kw):
        if cmd and cmd[0] == "gh":
            class Proc:
                returncode = gh_code
                stdout = (
                    ""
                    if gh_code
                    else json.dumps(
                        {
                            "headRefName": head or "",
                            "headRefOid": oid or "",
                            "isCrossRepository": False,
                        }
                    )
                )
                stderr = "" if gh_code == 0 else "missing"

            return Proc()
        return subprocess.run(cmd, **kw)

    return run


def test_fix_worktree_checks_out_pr_head_and_acks(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    _publish_head(clone, "fr-7888")
    oid = _head_oid(clone, "fr-7888")
    base = tmp_path / "worktrees"
    env = {"BOB_JOB_WORKTREE_BASE": str(base), "BOB_REPO_CLONE_bobiverse": str(clone)}
    line = "FROM jeeves #flamingo n: FIX SimonBarnett/bobiverse#7889 https://x"
    before = c.classify_opencode_job(line, env)
    assert before["state"] == "absent"
    ready = c.ensure_opencode_job_worktree(
        line, env, install_root=str(clone), run=_run_with_gh("fr-7888", oid), nick="flamingo-1"
    )
    assert ready["state"] == "project"
    assert ready["nack"] == ""
    path = Path(ready["path"])
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert head == "fr-7888"
    tip = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip().lower()
    assert tip == oid
    listed = subprocess.run(
        ["git", "-C", str(clone), "branch", "--list", "fix-7889"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert listed.strip() == ""
    written: list[str] = []
    relay = bw.Relay(log=lambda *_a, **_k: None, outbox_path=tmp_path / "outbox.txt")
    relay.write_outbox = lambda text: written.append(text) or True
    relay.set_target(lambda _line: True)
    relay.opencode_job_block = lambda raw: c.opencode_job_context_nack_ready(
        raw, env, install_root=str(clone), run=_run_with_gh("fr-7888", oid), nick="flamingo-1"
    )
    status = relay.deliver("jeeves", "#flamingo", "flamingo-1: FIX SimonBarnett/bobiverse#7889 https://x")
    assert status == "injected"
    assert any(item.startswith("ACK FIX SimonBarnett/bobiverse#7889") for item in written)
    assert not any("worktree-absent" in item for item in written)


def test_fix_missing_head_nacks_create_failed_not_absent(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"), "BOB_REPO_CLONE_bobiverse": str(clone)}
    line = "FROM jeeves #flamingo n: FIX SimonBarnett/bobiverse#7889 https://x"
    decision = c.ensure_opencode_job_worktree(
        line, env, install_root=str(clone), run=_run_with_gh(None, None, gh_code=1)
    )
    assert decision["state"] == "create_failed"
    assert "worktree-create-failed:pr-head" in decision["nack"]
    assert "worktree-absent" not in decision["nack"]


def test_mrb_fetch_failure_nacks_create_failed(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"), "BOB_REPO_CLONE_bobiverse": str(clone)}
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#50 https://x"
    fake_oid = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    def run(cmd, **kw):
        if cmd and cmd[0] == "gh":
            class Proc:
                returncode = 0
                stdout = json.dumps(
                    {
                        "headRefName": "fr-40",
                        "headRefOid": fake_oid,
                        "isCrossRepository": False,
                    }
                )
                stderr = ""

            return Proc()
        if cmd and "fetch" in cmd:
            class Proc:
                returncode = 1
                stdout = ""
                stderr = "fatal: couldn't find remote ref fr-40"

            return Proc()
        return subprocess.run(cmd, **kw)

    decision = c.ensure_opencode_job_worktree(line, env, install_root=str(clone), run=run)
    assert decision["state"] == "create_failed"
    assert "worktree-create-failed:fetch" in decision["nack"]
    assert "worktree-absent" not in decision["nack"]


def test_mrb7949_stale_local_fr_prefers_verified_sha(tmp_path: Path):
    """When local and origin/<head> both exist, worktree add must use verified SHA (FR #8022)."""
    clone = _init_clone(tmp_path / "clone")
    _publish_head(clone, "fr-7888")
    oid = _head_oid(clone, "fr-7888")
    subprocess.run(["git", "-C", str(clone), "branch", "fr-7888", "main"], check=True, capture_output=True)
    seen: list[list[str]] = []
    base_run = _run_with_gh("fr-7888", oid)

    def run(cmd, **kw):
        if cmd and cmd[0] == "git" and "worktree" in cmd and "add" in cmd:
            seen.append(list(cmd))
        return base_run(cmd, **kw)

    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"), "BOB_REPO_CLONE_bobiverse": str(clone)}
    line = "FROM jeeves #flamingo n: FIX SimonBarnett/bobiverse#7889 https://x"
    ready = c.ensure_opencode_job_worktree(
        line, env, install_root=str(clone), run=run, nick="flamingo-1"
    )
    assert ready["state"] == "project"
    assert seen, "expected a git worktree add"
    add = seen[-1]
    assert "-B" in add
    assert oid in add
    assert "origin/main" not in add

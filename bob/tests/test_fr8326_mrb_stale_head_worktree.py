"""FR #8326: stale PR-branch worktree must not block an MRB at headRefOid."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

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


def _publish(clone: Path, branch: str) -> str:
    subprocess.run(["git", "-C", str(clone), "checkout", "-b", branch], check=True, capture_output=True)
    (clone / "HEAD.txt").write_text(branch + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "HEAD.txt"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone), "commit", "-m", branch], check=True, capture_output=True)
    oid = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    subprocess.run(["git", "-C", str(clone), "checkout", "main"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone), "fetch", "origin", branch], check=True, capture_output=True)
    return oid


def _gh(head: str, oid: str):
    def run(cmd, **kw):
        if cmd and cmd[0] == "gh":
            class Proc:
                returncode = 0
                stdout = json.dumps(
                    {"headRefName": head, "headRefOid": oid, "isCrossRepository": False}
                )
                stderr = ""

            return Proc()
        return subprocess.run(cmd, **kw)

    return run


def test_fr8326_live_author_worktree_still_reviews_head(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    oid = _publish(clone, "fr-8298")
    author = tmp_path / "author-fr"
    subprocess.run(
        ["git", "-C", str(clone), "worktree", "add", str(author), "fr-8298"],
        check=True,
        capture_output=True,
    )
    (author / ".bobiverse-seat").write_text(
        json.dumps({"nick": "flamingo-dead", "pid": os.getpid(), "issue": 8298}),
        encoding="utf-8",
    )
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#8299 https://x"
    ready = c.ensure_opencode_job_worktree(
        line, env, install_root=str(clone), run=_gh("fr-8298", oid), nick="flamingo-12064"
    )
    assert ready["state"] == "project", ready
    assert author.is_dir()
    head = subprocess.run(
        ["git", "-C", str(ready["path"]), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    assert head == oid


def test_fr8326_head_mismatch_nack_names_both_shas():
    want = "a" * 40
    have = "b" * 40

    def run(cmd, **kw):
        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if cmd[:3] == ["git", "-C", "clone"] and "rev-parse" in cmd:
            Proc.stdout = have + "\n"
            return Proc()
        if "cat-file" in cmd:
            Proc.returncode = 1
            return Proc()
        if "fetch" in cmd:
            return Proc()
        Proc.returncode = 1
        return Proc()

    oid, err = c._fetch_pr_head_oid(
        run,
        "clone",
        branch="fr-8298",
        number="8299",
        want_oid=want,
        cross=False,
        fatal_fetch=True,
    )
    assert oid == ""
    assert err.startswith("head-mismatch")
    assert f"want={want}" in err
    assert f"have={have}" in err

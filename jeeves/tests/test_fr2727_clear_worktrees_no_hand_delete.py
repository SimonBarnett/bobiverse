"""FR #2727: Clear never selects operator/build trees; live seat markers skip even -Force.

Seats must not hand-delete arbitrary C:\\ai\\* paths when Clear removes 0 trees.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
MRB_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
SEAT_SKILL = (
    REPO / "bob" / "agents" / "worker" / ".grok" / "skills" / "bobiverse-worker-seat" / "SKILL.md"
)

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def _run_clear(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-RepoRoot",
        str(repo),
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return repo


def _add_wt(repo: Path, path: Path, branch: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-b", branch, str(path)],
        check=True,
        capture_output=True,
    )


def test_fr2727_script_excludes_operator_tree_names():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #2727" in text
    # Explicit denylist / never-select for operator build trees.
    assert "wt-bob-main" in text
    assert "wt-airc" in text
    assert "wt-main" in text
    assert "bobiverse-seat" in text.lower() or ".bobiverse-seat" in text


def test_fr2727_skills_cast_iron_no_hand_delete():
    for skill in (FR_SKILL, MRB_SKILL, SEAT_SKILL):
        assert skill.is_file(), skill
        text = skill.read_text(encoding="utf-8")
        assert "FR #2727" in text or "Clear-BobiverseJobWorktrees" in text
        low = text.lower()
        assert "never" in low and (
            "hand-delete" in low
            or "remove-item" in low
            or "did not select" in low
            or "clear did not" in low
        )
        # Manual one-liner must not invite deleting arbitrary trees.
        if skill == FR_SKILL:
            assert "only on your own job tree" in low or "own job tree" in low
            assert "arbitrary" in low or "did not select" in low or "hand-delete" in low


@WIN
def test_fr2727_clear_never_selects_wt_bob_main_or_airc(tmp_path: Path):
    """Registered trees named like operator builds must survive -Force reclaim."""
    repo = _init_repo(tmp_path)
    op_main = tmp_path / "wt-bob-main-b3f5057"
    op_airc = tmp_path / "wt-airc-2615"
    op_bare = tmp_path / "wt-main"
    job = tmp_path / "bobiverse-fr2727-job-wt"
    _add_wt(repo, op_main, "op-main-2727")
    _add_wt(repo, op_airc, "op-airc-2727")
    _add_wt(repo, op_bare, "op-bare-2727")
    _add_wt(repo, job, "fr-2727-job")
    keep = tmp_path / "keep"
    keep.mkdir()
    r = _run_clear(
        repo,
        "-KeepPath",
        str(keep),
        "-Force",
        "-MinFreeGB",
        "999",
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    out = (r.stdout or "") + (r.stderr or "")
    assert op_main.is_dir(), "wt-bob-main-* must never be removed"
    assert op_airc.is_dir(), "wt-airc-* must never be removed"
    assert op_bare.is_dir(), "wt-main must never be removed"
    assert not job.is_dir(), "real job tree should be reclaimable"
    assert "wt-bob-main" not in out.lower() or "skip" in out.lower() or op_main.is_dir()


@WIN
def test_fr2727_live_seat_marker_skipped_even_with_force(tmp_path: Path):
    """A job tree with .bobiverse-seat for this live PID must not be removed with -Force."""
    repo = _init_repo(tmp_path)
    live = tmp_path / "bobiverse-fr2727-live-wt"
    other = tmp_path / "bobiverse-fr2727-other-wt"
    _add_wt(repo, live, "fr-2727-live")
    _add_wt(repo, other, "fr-2727-other")
    marker = live / ".bobiverse-seat"
    marker.write_text(
        json.dumps({"nick": "marchhare-39556", "pid": os.getpid()}) + "\n",
        encoding="utf-8",
    )
    keep = tmp_path / "keep"
    keep.mkdir()
    r = _run_clear(
        repo,
        "-KeepPath",
        str(keep),
        "-Force",
        "-MinFreeGB",
        "999",
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert live.is_dir(), "live seat marker must skip removal even with -Force"
    assert not other.is_dir(), "unmarked job tree should still be removed"

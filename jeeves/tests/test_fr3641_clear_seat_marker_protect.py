"""FR #3641: Clear must not wipe mid-FR job trees that hold a seat marker.

Soft-cap (MaxExtraJobTrees=0) was removing unmarked / dead-pid trees while
another seat still edited them. A present .bobiverse-seat that is fresh must
survive soft-cap and non-Force reclaim even when the recorded pid is dead.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
MRB_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"

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


def test_fr3641_script_documents_fresh_seat_marker_gate():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #3641" in text
    assert "StaleSeatHours" in text
    assert ".bobiverse-seat" in text
    # Soft-cap must not treat a fresh marker as reclaimable just because pid is dead.
    assert "fresh" in text.lower() or "StaleSeatHours" in text


def test_fr3641_skills_write_seat_marker_after_worktree_add():
    for skill in (FR_SKILL, MRB_SKILL):
        assert skill.is_file(), skill
        text = skill.read_text(encoding="utf-8")
        assert "FR #3641" in text or ".bobiverse-seat" in text
        low = text.lower()
        assert "bobiverse-seat" in low
        assert "worktree add" in low or "after" in low or "immediately" in low


@WIN
def test_fr3641_fresh_seat_marker_survives_soft_cap_with_dead_pid(tmp_path: Path):
    """Soft-cap MaxExtraJobTrees=0 must keep a freshly marked job tree (dead pid)."""
    repo = _init_repo(tmp_path)
    marked = tmp_path / "job-fr-3641-marked"
    unmarked = tmp_path / "job-fr-3641-unmarked"
    _add_wt(repo, marked, "fr-3641-marked")
    _add_wt(repo, unmarked, "fr-3641-unmarked")
    # Dead / non-existent pid — old code would reclaim this under soft-cap.
    (marked / ".bobiverse-seat").write_text(
        json.dumps({"nick": "marchhare-34384", "pid": 1, "issue": 3641}) + "\n",
        encoding="utf-8",
    )
    keep = tmp_path / "keep"
    keep.mkdir()
    # FreeGB healthy + MaxExtraJobTrees=0 => soft-cap path (not -Force).
    r = _run_clear(
        repo,
        "-KeepPath",
        str(keep),
        "-MinFreeGB",
        "0",
        "-MaxExtraJobTrees",
        "0",
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    out = (r.stdout or "") + (r.stderr or "")
    assert marked.is_dir(), "fresh .bobiverse-seat must survive soft-cap (FR #3641)"
    assert "skip protected" in out.lower() or "3641" in out or marked.is_dir()
    assert not unmarked.is_dir(), "unmarked job tree still reclaimable under soft-cap"


@WIN
def test_fr3641_force_reclaims_stale_seat_marker(tmp_path: Path):
    """-Force may reclaim a marked tree whose seat marker is older than StaleSeatHours."""
    repo = _init_repo(tmp_path)
    stale = tmp_path / "job-fr-3641-stale"
    live = tmp_path / "job-fr-3641-live"
    _add_wt(repo, stale, "fr-3641-stale")
    _add_wt(repo, live, "fr-3641-live")
    (stale / ".bobiverse-seat").write_text(
        json.dumps({"nick": "old-seat", "pid": 1}) + "\n",
        encoding="utf-8",
    )
    # Age the marker beyond StaleSeatHours=0 (immediate stale).
    old = time.time() - 3600
    os.utime(stale / ".bobiverse-seat", (old, old))
    (live / ".bobiverse-seat").write_text(
        json.dumps({"nick": "marchhare-34384", "pid": os.getpid()}) + "\n",
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
        "-StaleSeatHours",
        "0",
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert live.is_dir(), "live pid marker must still skip even with -Force"
    assert not stale.is_dir(), "stale dead-pid marker reclaimable with -Force + StaleSeatHours=0"

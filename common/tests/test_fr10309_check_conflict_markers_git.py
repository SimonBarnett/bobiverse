"""FR #10309: check_conflict_markers scans git ls-files by default (not whole tree)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
import check_conflict_markers as ccm


def test_fr10309_defaults_to_git_tracked_in_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "clean.txt").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "clean.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "huge").mkdir()
    (repo / "huge" / "noise.txt").write_text("<<<<<<< HEAD\n", encoding="utf-8")
    files = ccm.iter_files(repo, None)
    assert len(files) == 1
    assert files[0].name == "clean.txt"
"""FR #7653: do not offer FIX for a pull that is already merged or closed."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

gitclaim = importlib.import_module("gitclaim")
mog = importlib.import_module("mrb_merge_on_green")

REPO = "SimonBarnett/priority-mcp"
SHA = "b" * 40


def test_fix_is_dead_matches_repo_case():
    row = {"task": "FIX", "repo": REPO, "id": "#641"}
    dead = gitclaim._fix_is_dead(
        row,
        open_pulls={REPO.lower(): set()},
        fetched_repos={REPO.lower()},
    )
    assert dead is True


def test_enqueue_conflict_fix_skips_merged_pr(tmp_path: Path):
    result = mog.enqueue_conflict_fix(
        tmp_path,
        repo=REPO,
        pr="641",
        pass_sha=SHA,
        pr_state={"merged": True, "closed": True, "state": "closed", "title": "FR"},
    )
    assert result == "skipped"


def test_enqueue_mrb_fail_fix_skips_closed_pr(tmp_path: Path):
    result = mog.enqueue_mrb_fail_fix(
        tmp_path,
        repo=REPO,
        pr="641",
        sha=SHA,
        pr_state={"closed": True, "state": "closed", "title": "FR", "labels": []},
    )
    assert result == "skipped"

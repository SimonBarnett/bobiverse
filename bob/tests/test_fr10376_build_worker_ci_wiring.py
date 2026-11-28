"""FR #10376: build-bob-worker must run off-thread worktree pytest gates on CI."""
from __future__ import annotations

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-worker.yml"


def test_fr10376_workflow_path_filters_include_off_thread_tests():
    text = WF.read_text(encoding="utf-8")
    for needle in (
        "bob/tests/test_fr10360_job_worktree_git_off_thread.py",
        "bob/tests/test_fr6328_opencode_worktree_off_thread.py",
    ):
        assert needle in text, f"missing path filter: {needle}"


def test_fr10376_workflow_runs_off_thread_pytest_job():
    text = WF.read_text(encoding="utf-8")
    assert "python -m pytest" in text
    assert "test_fr10360_job_worktree_git_off_thread.py" in text
    assert "test_fr6328_opencode_worktree_off_thread.py" in text

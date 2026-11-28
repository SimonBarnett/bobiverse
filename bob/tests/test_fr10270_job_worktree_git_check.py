"""FR #10270: seat start verifies git in the job worktree, repairs the admin dir (FR #10244 helper)
or files intake when git is still broken."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
sys.path.insert(0, str(ROOT / "bob" / "scripts"))

import bob_worker as bw  # noqa: E402


def _rc(argv, code):
    return subprocess.CompletedProcess(argv, code, "", "")


def _git_run(ok_sequence):
    """Return a run() stub that answers `git rev-parse --git-dir` from ok_sequence (bools, in call order)."""
    calls = []
    seq = list(ok_sequence)

    def run(argv, **kwargs):
        calls.append(list(argv))
        if "rev-parse" in argv and "--git-dir" in argv:
            ok = seq.pop(0) if seq else False
            return _rc(argv, 0 if ok else 128)
        return _rc(argv, 0)

    run.calls = calls
    return run


def test_ok_when_git_works_no_repair_no_intake(tmp_path: Path):
    wt = tmp_path / "fr-10270"
    wt.mkdir()
    run = _git_run([True])
    seen = []
    state = bw.verify_job_worktree_git(
        wt,
        run=run,
        repair=lambda p: seen.append(p) or "repaired",
        intake=lambda *a, **k: seen.append("intake") or True,
        log=lambda m: None,
    )
    assert state == "ok"
    assert seen == []


def test_repaired_when_admin_fixed_and_git_works(tmp_path: Path):
    wt = tmp_path / "fr-10270"
    wt.mkdir()
    run = _git_run([False, True])
    intake_calls = []
    state = bw.verify_job_worktree_git(
        wt,
        run=run,
        repair=lambda p: "repaired",
        intake=lambda *a, **k: intake_calls.append(a) or True,
        log=lambda m: None,
    )
    assert state == "repaired"
    assert intake_calls == []


def test_git_still_broken_files_intake(tmp_path: Path):
    wt = tmp_path / "fr-10270"
    wt.mkdir()
    run = _git_run([False, False])
    intake_calls = []
    state = bw.verify_job_worktree_git(
        wt,
        run=run,
        repair=lambda p: "branch-missing",
        intake=lambda path, state, detail, **k: intake_calls.append((state, detail)) or True,
        log=lambda m: None,
    )
    assert state == "git-still-broken"
    assert intake_calls == [("git-still-broken", "branch-missing")]


def test_helper_missing_on_main_files_intake(tmp_path: Path):
    wt = tmp_path / "fr-10270"
    wt.mkdir()
    run = _git_run([False])
    intake_calls = []
    state = bw.verify_job_worktree_git(
        wt,
        run=run,
        repair=lambda p: "helper-missing",
        intake=lambda path, state, detail, **k: intake_calls.append(state) or True,
        log=lambda m: None,
    )
    assert state == "helper-missing"
    assert intake_calls == ["helper-missing"]


def test_missing_worktree_is_not_repaired(tmp_path: Path):
    seen = []
    state = bw.verify_job_worktree_git(
        tmp_path / "does-not-exist",
        run=_git_run([]),
        repair=lambda p: seen.append(p) or "repaired",
        intake=lambda *a, **k: True,
        log=lambda m: None,
    )
    assert state == "no-worktree"
    assert seen == []


def test_repair_helper_missing_when_common_ps1_absent(tmp_path: Path):
    state = bw.repair_job_worktree_admin(
        tmp_path,
        run=_git_run([]),
        common_ps1=tmp_path / "no-such" / "Bobiverse-Common.ps1",
    )
    assert state == "helper-missing"


def test_repair_parses_last_state_token(tmp_path: Path):
    common = tmp_path / "Bobiverse-Common.ps1"
    common.write_text("# stub\n", encoding="ascii")
    captured = {}

    def run(argv, **kwargs):
        captured["argv"] = list(argv)
        return subprocess.CompletedProcess(argv, 0, "noise\nrepaired\n", "")

    state = bw.repair_job_worktree_admin(tmp_path, run=run, common_ps1=common)
    assert state == "repaired"
    joined = " ".join(captured["argv"])
    assert "Repair-BobiverseJobWorktreeAdmin" in joined
    assert "-WorktreePath" in joined


def test_intake_argv_pins_repo_and_kind(tmp_path: Path):
    captured = {}

    def run(argv, **kwargs):
        captured["argv"] = list(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    ok = bw.file_job_worktree_git_intake(
        tmp_path / "fr-10270", "git-still-broken", "branch-missing", run=run
    )
    assert ok is True
    argv = captured["argv"]
    assert argv[argv.index("-Repo") + 1] == "SimonBarnett/bobiverse"
    assert argv[argv.index("-Kind") + 1] == "issue"
    assert "Report-BobiverseIntakeIssue.ps1" in " ".join(argv)

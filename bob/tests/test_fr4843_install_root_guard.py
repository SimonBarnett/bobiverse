"""FR #4843: install-root job-git refuse + seat-start branch warning."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
sys.path.insert(0, str(ROOT / "bob" / "scripts"))

import bob_install_root_guard as guard  # noqa: E402
import bob_worker as bw  # noqa: E402


class _FakeRun:
    """Map (cwd, argv-tail) -> CompletedProcess."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls = []

    def __call__(self, argv, capture_output=True, text=True, timeout=15, check=False, **kwargs):
        self.calls.append(list(argv))
        key = tuple(argv)
        if key in self.answers:
            code, out, err = self.answers[key]
            return subprocess.CompletedProcess(argv, code, out, err)
        # Allow lookup by (git, -C, path, ...rest)
        return subprocess.CompletedProcess(argv, 1, "", "not stubbed")


def test_refuse_checkout_b_in_install_root(tmp_path: Path):
    install = tmp_path / "bob"
    install.mkdir()
    job = tmp_path / "bob-wt-fr-4843"
    job.mkdir()

    def run(argv, **kwargs):
        # toplevel for install and its child paths -> install
        if argv[:3] == ["git", "-C", str(install.resolve())] and "rev-parse" in argv:
            if "--show-toplevel" in argv:
                return subprocess.CompletedProcess(argv, 0, str(install.resolve()) + "\n", "")
        if len(argv) >= 3 and argv[0] == "git" and argv[1] == "-C":
            cwd = Path(argv[2])
            if "--show-toplevel" in argv:
                try:
                    cwd.resolve().relative_to(install.resolve())
                    return subprocess.CompletedProcess(argv, 0, str(install.resolve()) + "\n", "")
                except ValueError:
                    return subprocess.CompletedProcess(argv, 0, str(cwd.resolve()) + "\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "fail")

    msg = guard.refuse_job_git(
        op="checkout -b fr-4843",
        target=install,
        install_root=install,
        issue_n=4843,
        run=run,
    )
    assert msg is not None
    assert "FR #4843" in msg
    assert "refuse git checkout" in msg
    assert "bob-wt-fr-4843" in msg
    assert str(install.resolve()) in msg

    ok = guard.refuse_job_git(
        op="checkout -b fr-4843",
        target=job,
        install_root=install,
        issue_n=4843,
        run=run,
    )
    assert ok is None


def test_refuse_commit_under_install_worker_cwd(tmp_path: Path):
    install = tmp_path / "bob"
    worker = install / "worker"
    worker.mkdir(parents=True)

    def run(argv, **kwargs):
        if "--show-toplevel" in argv:
            return subprocess.CompletedProcess(argv, 0, str(install.resolve()) + "\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "")

    msg = guard.refuse_job_git(
        op="commit",
        target=worker,
        install_root=install,
        issue_n=4827,
        run=run,
    )
    assert msg is not None
    assert "refuse git commit" in msg


def test_allow_status_and_foreign_worktree(tmp_path: Path):
    install = tmp_path / "bob"
    install.mkdir()
    other = tmp_path / "other-wt"
    other.mkdir()

    def run(argv, **kwargs):
        if argv[2] == str(other.resolve()) or Path(argv[2]).resolve() == other.resolve():
            return subprocess.CompletedProcess(argv, 0, str(other.resolve()) + "\n", "")
        return subprocess.CompletedProcess(argv, 0, str(install.resolve()) + "\n", "")

    assert guard.refuse_job_git(op="status", target=install, install_root=install, run=run) is None
    assert guard.refuse_job_git(op="commit", target=other, install_root=install, run=run) is None


def test_install_root_branch_warning_on_fr_branch(tmp_path: Path):
    install = tmp_path / "bob"
    install.mkdir()

    def run(argv, **kwargs):
        if "--abbrev-ref" in argv:
            return subprocess.CompletedProcess(argv, 0, "fr-4827\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "")

    warn = guard.install_root_branch_warning(install, run=run)
    assert warn is not None
    assert "WARN FR #4843" in warn
    assert "branch=fr-4827" in warn
    assert "expected=main" in warn

    def run_main(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "main\n", "")

    assert guard.install_root_branch_warning(install, run=run_main) is None


def test_suggest_job_worktree_sibling_style(tmp_path: Path):
    install = tmp_path / "ai" / "bob"
    install.mkdir(parents=True)
    tip = guard.suggest_job_worktree(install, mode="fr", issue_n=4843)
    assert tip.endswith(str(Path("bob-wt-fr-4843")))
    assert Path(tip).parent == install.parent


def test_bob_worker_logs_install_root_branch_warning(tmp_path: Path):
    install = tmp_path / "bob"
    install.mkdir()
    logs: list[str] = []

    def run_fr(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "fr-4827\n", "")

    assert hasattr(bw, "log_install_root_guard")
    msg = bw.log_install_root_guard(install, log=logs.append, run=run_fr)
    assert msg is not None
    assert "FR #4843" in msg
    assert "fr-4827" in msg
    assert any("FR #4843" in x for x in logs)

    logs.clear()
    def run_main(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "main\n", "")

    assert bw.log_install_root_guard(install, log=logs.append, run=run_main) is None
    assert logs == []


def test_worker_prompt_mentions_install_root_cast_iron():
    text = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "box", "box-1")
    assert "FR #4843" in text or "install root" in text.lower()
    assert "worktree" in text.lower()

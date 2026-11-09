"""docs/mrb-6324: leaf-only BOB_REPO_CLONE_* + _git_run UTF-8 (MRB #6324 amber)."""
from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

import opencode_seat_contract as c  # noqa: E402


def _init_clone(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@t"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "t"],
        check=True,
        capture_output=True,
    )
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "i"],
        check=True,
        capture_output=True,
    )
    return path


def test_docs_mrb6324_bare_bob_repo_clone_ignored(tmp_path: Path):
    wrong = _init_clone(tmp_path / "wrong-repo")
    env = {"BOB_REPO_CLONE": str(wrong)}
    assert c.resolve_repo_clone("SimonBarnett/a-search", env) == ""
    env2 = {"BOB_REPO_CLONE": str(wrong), "BOB_REPO_CLONE_bobiverse": str(wrong)}
    assert c.resolve_repo_clone("SimonBarnett/bobiverse", env2) == str(wrong)


def test_docs_mrb6324_git_run_requests_utf8():
    src = inspect.getsource(c._git_run)
    assert 'encoding="utf-8"' in src or "encoding='utf-8'" in src
    assert "errors=" in src


class _FakeProc:
    def __init__(self, stdout, stderr=b"", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_docs_mrb6324_git_run_replaces_invalid_utf8():
    """Invalid UTF-8 from git must be replaced; _git_run must not raise."""
    bad = b"ok-\xff-tail"

    def fake_run(args, **kwargs):
        assert kwargs.get("encoding") in ("utf-8", "utf8")
        assert kwargs.get("errors") == "replace"
        text = bad.decode(kwargs["encoding"], errors=kwargs["errors"])
        return _FakeProc(text)

    proc = c._git_run(fake_run, ["git", "status"])
    assert isinstance(proc.stdout, str)
    assert "\ufffd" in proc.stdout
    assert proc.stdout.startswith("ok-")
    assert "tail" in proc.stdout


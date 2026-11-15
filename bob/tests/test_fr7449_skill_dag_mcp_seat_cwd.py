"""FR #7449: skill_dag_mcp accepts --seat-cwd (ignored marker from bob_worker launch argv)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import skill_dag_mcp as mcp

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "bob" / "scripts" / "skill_dag_mcp.py"
ROOT = REPO / "bob" / ".grok" / "skills"


def test_fr7449_roots_from_argv_accepts_seat_cwd(tmp_path: Path):
    ptr = tmp_path / "ptr"
    ptr.write_text("", encoding="utf-8")
    roots = mcp.roots_from_argv(
        [
            f"--root={ROOT.as_posix()}",
            "--job-worktree-file",
            ptr.as_posix(),
            "--seat-cwd",
            str(tmp_path / "bound-cwd"),
        ]
    )
    assert any(Path(r).resolve() == ROOT.resolve() for r in roots)


def test_fr7449_once_status_with_seat_cwd_exits_zero():
    assert SCRIPT.is_file()
    assert ROOT.is_dir()
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(ROOT),
            "--job-worktree-file",
            "NUL" if sys.platform.startswith("win") else "/dev/null",
            "--seat-cwd",
            r"C:\tmp\bound-cwd",
            "--once",
            "status",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "ok" in data or "roots" in data or "tools" in data or isinstance(data, dict)

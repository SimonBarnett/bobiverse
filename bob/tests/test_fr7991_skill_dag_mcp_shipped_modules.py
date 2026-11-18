"""FR #7991: the shipped skill-dag MCP must import the same modules as the CLI.

``skill_dag_mcp.py`` imports ``skill_dag_index`` from its own scripts dir. The
one-shot CLI works because the interpreter adds that dir to ``sys.path``; the
frozen worker shipped only ``skill_dag_mcp.py``, so the MCP host saw an empty
index whose ``last_error`` was just ``ModuleNotFoundError``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import skill_dag_mcp as mcp
import worker_shipped_scripts as ship

from repo_layout import ROOT

BOB_SCRIPTS = ROOT / "bob" / "scripts"
WORKER = BOB_SCRIPTS / "bob_worker.py"


def test_fr7991_ships_sibling_modules_of_by_path_scripts():
    names = ship.shipped_script_names(WORKER, BOB_SCRIPTS)
    assert "skill_dag_mcp.py" in names
    assert "skill_dag_index.py" in names
    for name in names:
        assert ship.find_module_file(name, BOB_SCRIPTS) is not None, name


def test_fr7991_copy_and_check_include_sibling(tmp_path: Path):
    dest = tmp_path / "scripts"
    names = ship.copy_by_path_scripts(WORKER, BOB_SCRIPTS, dest)
    assert "skill_dag_index.py" in names
    assert (dest / "skill_dag_index.py").is_file()
    assert ship.check_by_path_scripts(WORKER, dest, source_dir=BOB_SCRIPTS) == names
    (dest / "skill_dag_index.py").unlink()
    try:
        ship.check_by_path_scripts(WORKER, dest, source_dir=BOB_SCRIPTS)
    except SystemExit as exc:
        assert "skill_dag_index.py" in str(exc)
    else:
        raise AssertionError("check must fail when a sibling module is absent")


def test_fr7991_transitive_local_sibling_closure(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (tmp_path / "bob_worker.py").write_text(
        '_resolve_installed_worker_script("entry.py")\n', encoding="utf-8"
    )
    (src / "entry.py").write_text("from middle import thing\n", encoding="utf-8")
    (src / "middle.py").write_text("import leaf\n", encoding="utf-8")
    (src / "leaf.py").write_text("thing = 1\n", encoding="utf-8")
    (src / "unrelated.py").write_text("", encoding="utf-8")
    names = ship.shipped_script_names(tmp_path / "bob_worker.py", src)
    # FR #7991: transitive sibling .py closure.
    assert "entry.py" in names and "middle.py" in names and "leaf.py" in names
    assert "unrelated.py" not in names
    # FR #8156 / #8206: fleet .ps1 helpers are always included even in tiny fixtures.
    for ps1 in ship.fleet_ps1_script_names():
        assert ps1 in names
    assert names == sorted(
        ["entry.py", "leaf.py", "middle.py"] + list(ship.fleet_ps1_script_names())
    )


def test_fr7991_status_names_the_missing_module(tmp_path: Path):
    lone = tmp_path / "lone"
    lone.mkdir()
    (lone / "skill_dag_mcp.py").write_bytes(
        (BOB_SCRIPTS / "skill_dag_mcp.py").read_bytes()
    )
    root = tmp_path / "skills"
    root.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
    proc = subprocess.run(
        [
            sys.executable,
            str(lone / "skill_dag_mcp.py"),
            "--once",
            "status",
            "--root",
            str(root),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    status = json.loads(proc.stdout.strip().splitlines()[-1])
    assert status["node_count"] == 0
    assert "skill_dag_index" in status["last_error"]
    assert status["last_error"].startswith("ModuleNotFoundError")


def test_fr7991_cli_status_is_empty_error(tmp_path: Path):
    """The repo copy (sibling present) still indexes cleanly."""
    server = mcp.SkillDagServer(roots=[tmp_path / "skills"])
    assert server.last_error == ""

def test_mrb7994_list_cli_without_source_dir_includes_sibling():
    """Build-BobWorker.ps1 calls --list with only --bob-worker (FR #7991)."""
    proc = subprocess.run(
        [
            sys.executable,
            str(BOB_SCRIPTS / "worker_shipped_scripts.py"),
            "--list",
            "--bob-worker",
            str(WORKER),
        ],
        cwd=str(BOB_SCRIPTS),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    listed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert "skill_dag_mcp.py" in listed
    assert "skill_dag_index.py" in listed
    assert "sys.py" not in listed
    assert "json.py" not in listed

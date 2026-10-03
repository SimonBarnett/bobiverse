"""FR #963: repo_layout importable from common/scripts in sparse trees (no common/tests required)."""
from __future__ import annotations

import importlib
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from repo_layout import REPO, ROOT

SERVICES = ("jeeves", "bob", "airc")


def test_canonical_repo_layout_lives_in_common_scripts():
    canon = REPO / "common" / "scripts" / "repo_layout.py"
    assert canon.is_file(), "canonical repo_layout must live in common/scripts (FR #963)"
    text = canon.read_text(encoding="utf-8")
    assert "REPO" in text and "Legacy" in text
    # parents[2] == repo root for both common/scripts and common/tests locations
    assert "parents[2]" in text


def test_compat_shim_in_common_tests_points_at_scripts():
    shim = REPO / "common" / "tests" / "repo_layout.py"
    assert shim.is_file()
    text = shim.read_text(encoding="utf-8")
    assert "FR #963" in text
    assert "common/scripts" in text or "scripts" in text


@pytest.mark.parametrize("svc", SERVICES)
def test_service_conftest_adds_common_scripts(svc: str):
    p = REPO / svc / "tests" / "conftest.py"
    assert p.is_file(), p
    text = p.read_text(encoding="utf-8")
    assert "FR #963" in text
    assert "common" in text and "scripts" in text


def test_root_conftest_prefers_scripts_for_repo_layout():
    text = (REPO / "conftest.py").read_text(encoding="utf-8")
    assert "FR #963" in text
    assert "common" in text and "scripts" in text
    # scripts entries appear before the trailing common/tests append
    i_scripts = text.find('for s in ("airc", "bob", "jeeves", "common")')
    i_tests = text.find('common" / "tests"')
    if i_tests < 0:
        i_tests = text.find("common' / 'tests'")
    assert i_scripts >= 0 and i_tests >= 0 and i_scripts < i_tests


def test_import_repo_layout_with_only_common_scripts_on_path(tmp_path: Path):
    """Simulate sparse MRB tree: common/scripts present, common/tests absent from PYTHONPATH."""
    env = dict(**{k: v for k, v in __import__("os").environ.items() if k.upper() != "PYTHONPATH"})
    env["PYTHONPATH"] = str(REPO / "common" / "scripts")
    code = textwrap.dedent(
        """
        from repo_layout import REPO, ROOT
        assert REPO.is_dir()
        assert (REPO / "common" / "scripts" / "repo_layout.py").is_file()
        print("ok", REPO)
        """
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(REPO))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok" in r.stdout


def test_pytest_collects_with_service_conftest_without_root(tmp_path: Path):
    """jeeves/tests/conftest.py alone is enough when common/scripts exists (no root conftest)."""
    # Run a one-off collection of a tiny inline test under a copy? Use existing smoke via -c.
    # Instead: import the service conftest path logic by running pytest on this file's sibling with --noconftest
    # from repo root would still load root. Use subprocess cwd + PYTHONPATH empty + only jeeves tree...
    env = dict(**{k: v for k, v in __import__("os").environ.items() if k.upper() != "PYTHONPATH"})
    # Clear path; rely on jeeves/tests/conftest.py
    probe = REPO / "jeeves" / "tests" / "_fr963_probe_import.py"
    probe.write_text(
        "from repo_layout import REPO\n\ndef test_probe():\n    assert REPO.is_dir()\n",
        encoding="utf-8",
    )
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-q", "--noconftest"],
            capture_output=True,
            text=True,
            cwd=str(REPO),
            env=env,
        )
        # --noconftest skips ALL conftest including service; so this should FAIL without PYTHONPATH.
        # Real check: WITHOUT --noconftest but with confcutdir=jeeves/tests
        r2 = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(probe),
                "-q",
                "--confcutdir",
                str(REPO / "jeeves" / "tests"),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO),
            env=env,
        )
        assert r2.returncode == 0, r2.stdout + r2.stderr
    finally:
        if probe.exists():
            probe.unlink()


def test_job_skills_mention_sparse_repo_layout():
    fr = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
    mrb = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
    for p in (fr, mrb):
        assert p.is_file(), p
        t = p.read_text(encoding="utf-8")
        assert "repo_layout" in t or "common/scripts" in t
        assert "963" in t or "sparse" in t.lower()
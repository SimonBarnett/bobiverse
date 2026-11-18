"""FR #8157: select_tests maps changed files to a bounded in-job pytest set."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import select_tests as st

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "common" / "scripts"


def test_fr8157_gitclaim_changed_maps_under_50_with_offer_order():
    """AC3: fixture touching gitclaim.py -> <50 files including offer-order tests."""
    selected = st.map_changed_to_tests(
        ["common/scripts/gitclaim.py"],
        REPO,
        max_files=st.DEFAULT_MAX,
    )
    assert selected, "expected at least one mapped test"
    assert len(selected) < 50
    joined = "\n".join(selected).lower()
    assert "offer_order" in joined or "offer-order" in joined
    assert any("gitclaim" in p.lower() or "offer_order" in p.lower() for p in selected)


def test_fr8157_cli_files_gitclaim_bounded(tmp_path=None):
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "select_tests.py"),
            "--repo-root",
            str(REPO),
            "--files",
            "common/scripts/gitclaim.py",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stderr
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    assert 0 < len(lines) < 50
    blob = "\n".join(lines).lower()
    assert "offer_order" in blob or "gitclaim" in blob


def test_fr8157_looks_like_full_suite_argv():
    assert st.looks_like_full_suite_argv([]) is True
    assert st.looks_like_full_suite_argv(["-q"]) is True
    assert st.looks_like_full_suite_argv(["jeeves/tests"]) is True
    assert st.looks_like_full_suite_argv(["common/tests", "-q"]) is True
    assert st.looks_like_full_suite_argv(["bob/tests/test_fr8157_select_tests.py"]) is False
    assert st.looks_like_full_suite_argv(["-k", "foo"]) is True  # no path => full
    assert st.looks_like_full_suite_argv(["-k", "foo", "jeeves/tests/test_x.py"]) is False


def test_fr8157_check_full_suite_cli_exits_2():
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "select_tests.py"),
            "--check-full-suite",
            "jeeves/tests",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO),
    )
    assert proc.returncode == 2
    assert "8157" in (proc.stderr or "")


def test_fr8157_check_full_suite_cli_ok_for_file():
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "select_tests.py"),
            "--check-full-suite",
            "bob/tests/test_fr8157_x.py",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO),
    )
    assert proc.returncode == 0


def test_fr8157_changed_test_file_is_selected():
    selected = st.map_changed_to_tests(
        ["common/tests/test_fr8157_select_tests.py"],
        REPO,
    )
    assert "common/tests/test_fr8157_select_tests.py" in [
        p.replace("\\", "/") for p in selected
    ]

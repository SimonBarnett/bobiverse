"""FR #8157: run_job_pytest blocks full suites; skills + rules_text guide targeted runs."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import bob_worker as bw

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "common" / "scripts"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
MRB_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"


def test_fr8157_run_job_pytest_blocks_full_suite():
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "run_job_pytest.py"), "-q", "jeeves/tests"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO),
    )
    assert proc.returncode == 2
    err = proc.stderr or ""
    assert "8157" in err
    assert "full-suite" in err.lower() or "blocked" in err.lower()


def test_fr8157_run_job_pytest_blocks_bare():
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "run_job_pytest.py")],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO),
    )
    assert proc.returncode == 2


def test_fr8157_fr_skill_targets_not_whole_suite():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "Run the whole suite (not just yours)" not in text
    assert "select_tests.py --changed" in text
    assert "Targeted in-job tests (FR #8157)" in text
    assert "600" in text


def test_fr8157_mrb_skill_targets_keeps_airc_carveout():
    text = MRB_SKILL.read_text(encoding="utf-8")
    assert "FR #8157" in text
    assert "select_tests.py --changed" in text
    assert "FR #2655" in text
    assert "airc/tests" in text
    assert "Targeted in-job tests (FR #8157)" in text


def test_fr8157_rules_text_mentions_targeted_pytest():
    text = bw.rules_text(r"C:\ai\bob\worker", "agent")
    assert "8157" in text
    assert "select_tests.py" in text
    assert "jeeves/tests" in text

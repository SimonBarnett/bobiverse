"""FR #4484: FAIL-supersede + restates main / admit main already has must SKIP.

Class of filing in_0c5431ad1b93463a which opened a-search#3470. Those phrases
are not "already on main", "second copy", or "job-mrb", so the existing
thin-twin cues missed them.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

SUMMARY = (
    "MRB FAIL-supersede: the tip restates main seat-nick GIVEUP and was closed unmerged"
)
LESSON = (
    "admit main already has the Self-MRB GIVEUP wire; do not file another harvest tip"
)


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST_PS1),
            *extra,
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )


def test_fr4484_script_documents_restates_main_skip():
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "FR #4484" in text
    assert "restates main" in text.lower() or "restate" in text
    assert "admit main already has" in text.lower() or "admit\\s+main\\s+already\\s+has" in text


def test_fr4484_intake_detects_restates_main_and_admit():
    assert intake.is_fail_supersede_thin_twin_lesson(SUMMARY + "\n" + LESSON)
    assert intake.is_fail_supersede_thin_twin_lesson(
        "FAIL-supersede: this receipt restates main"
    )
    assert intake.is_fail_supersede_thin_twin_lesson(
        "FAIL-superseded. admit main already has the twin-close filter"
    )
    assert not intake.is_fail_supersede_thin_twin_lesson(
        "The provider restates main marketplace fields in the fixture"
    )


def test_fr4484_harvest_skips_restates_main(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        SUMMARY,
        "-Lesson",
        LESSON,
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr4484_restates_main_without_fail_supersede_still_posts(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "The provider restates main marketplace fields in the fixture",
        "-Lesson",
        "Keep the fixture field names aligned with the live response shape",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout

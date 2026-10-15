"""MRB #4359 hostile pins for FR #4357 harvest lesson-MRB PASS skip."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
SKILL = ROOT / ".grok" / "skills" / "harvest" / "SKILL.md"


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            *extra,
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )


def test_skill_fr4357_bullet_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4357" in text
    assert "SKIPPED harvest lesson-MRB PASS loop" in text or "lesson-MRB PASS loop" in text
    # Contiguous playbook needle from the harvested bullet
    assert "stops a-search tip flood" in text or "tip flood after light-triage PASS" in text
    raw = SKILL.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"


def test_process_cues_alone_do_not_skip(tmp_path: Path):
    """merge origin/main + re-arm without harvest-lesson/docs/mrb still files."""
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "MRB bobiverse#4000 product FR: merge origin/main, re-arm --auto --squash, DONE PASS",
        "-Lesson",
        "Keep-both skill-harvest-log dated sections when CONFLICTING; re-arm both tips.",
        "-OutboxDir",
        str(tmp_path / "out"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson-MRB PASS loop" not in r.stdout


def test_lesson_pass_without_process_cues_does_not_skip(tmp_path: Path):
    """harvest-lesson + PASS without merge/re-arm/keep-both still attempts file."""
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "MRB a-search#1990 harvest-lesson light triage PASS only; no rebase needed",
        "-Lesson",
        "Harvest-lesson tip was current with main; light triage PASS.",
        "-OutboxDir",
        str(tmp_path / "out"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson-MRB PASS loop" not in r.stdout


def test_three_gates_present_in_script():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "Test-HarvestLessonMrbPassLoop" in text
    # All three gate families must remain for the AND skip
    assert "harvest[- ]lesson" in text or "harvest-lesson" in text
    assert "docs/mrb" in text
    assert "merge\\s+origin/main" in text or "merge origin/main" in text
    assert "re-arm" in text
    assert "keep-both" in text

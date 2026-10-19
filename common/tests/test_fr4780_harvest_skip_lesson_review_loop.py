"""FR #4780: MRB of a harvest-lesson / skills-only PR must not spawn a new lesson tip.

Honesty-box for reviewing lessons is the review itself. Skip:
- lesson-review / closing / harvesting-lessons meta subjects
- MRB DONE/CLOSED/FAIL on harvest-lesson tips (any outcome, not only PASS+process)
- 24h dedup against open and closed harvest-lesson PRs with the same lesson text

Acceptance test: simulate MRB DONE on a lesson PR -> no new harvest PR/issue queued.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST.is_file():
    HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


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
        timeout=90,
        cwd=str(ROOT),
    )


def test_fr4780_script_documents_lesson_review_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #4780" in text
    assert "Test-HarvestLessonReviewLoop" in text
    assert "SKIPPED harvest lesson-review loop" in text
    assert "Test-HarvestRecentLessonDedup" in text or "24h" in text.lower() or "24 h" in text


def test_fr4780_mrb_done_on_lesson_pr_does_not_queue(tmp_path: Path):
    """Simulate MRB DONE on a harvest-lesson tip: no new tip filed."""
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "MRB #4772 PASS CLOSED not-useful harvest-lesson tip-loop meta twin of #4769",
        "-Lesson",
        "Harvest tip that only restates twin FAIL-supersede for FR #3991 example: close citing bobiverse-bob-job-mrb; do not merge process meta",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson-review loop" in r.stdout or "SKIPPED harvest" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_fr4780_skips_closed_not_useful_lesson_review(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "MRB #4779 CLOSED not-useful: tip-loop twin FAIL-supersede meta; durable in bobiverse-bob-job-mrb",
        "-Lesson",
        "When two harvest tips race the same playbook, FAIL-supersede the later tip citing the merged first; do not land a second Harvested-lessons bullet",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr4780_skips_reviewing_harvesting_closing_lessons_subject(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "After reviewing harvest-lesson PRs, note how closing lesson tips works",
        "-Lesson",
        "When reviewing or closing harvest-lesson tips, do not harvest a new lesson about reviewing lessons",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson-review loop" in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr4780_genuine_product_playbook_still_attempts_post(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Summary",
        "Pack stage: SkipAircNetworkInstallerExe with SkipMsi for disposable airc stage tests",
        "-Lesson",
        "Pack-BobiverseRelease: -SkipAircNetworkInstallerExe requires -SkipMsi so disposable stages skip UAC installer PyInstaller.",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson-review loop" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout


def test_fr4780_intake_detects_lesson_review_meta():
    import intake

    assert intake.is_lesson_review_meta_loop(
        "MRB #4772 PASS CLOSED not-useful harvest-lesson\n"
        "Harvest tip that only restates twin FAIL-supersede; do not merge process meta"
    )
    assert intake.is_lesson_review_meta_loop(
        "When reviewing harvest-lesson tips, do not harvest a new lesson about closing lessons"
    )
    assert not intake.is_lesson_review_meta_loop(
        "Pack-BobiverseRelease: -SkipAircNetworkInstallerExe requires -SkipMsi for stage tests"
    )

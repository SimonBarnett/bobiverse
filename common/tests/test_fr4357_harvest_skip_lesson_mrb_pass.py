"""FR #4357: harvest must not open a new tip after PASS of a harvest-lesson / docs/mrb MRB."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

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
        timeout=60,
        cwd=str(ROOT),
    )


def test_harvest_script_documents_lesson_mrb_pass_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #4357" in text
    assert "Test-HarvestLessonMrbPassLoop" in text
    assert "SKIPPED harvest lesson-MRB PASS loop" in text


def test_harvest_skips_harvest_lesson_reoffer_pass(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "MRB re-offer a-search#1990 FR-216 madeiradb docs-pin harvest-lesson: tip 1 behind merged; docs/mrb #2289 synced hostile pass; DONE PASS",
        "-Lesson",
        "Harvest-lesson re-offer with existing docs/mrb: merge origin/main on skill+docs tips when behind, re-arm both --auto --squash, DONE PASS (FR #3317/#3948)",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson-MRB PASS loop" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout


def test_harvest_skips_docs_mrb_conflicting_pass(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "MRB re-offer a-search#2038 CLOSED-superseded docs/mrb harvest-lesson: CONFLICTING resolved fr106/108 ours; 19 pass; DONE PASS",
        "-Lesson",
        "Harvest-lesson tip CONFLICTING on fr106/108: merge origin/main, --ours enabled=true, re-arm --auto --squash, DONE PASS (FR #3317/#3948)",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson-MRB PASS loop" in r.stdout


def test_harvest_still_posts_genuine_new_playbook(tmp_path: Path):
    """A real new product playbook (not MRB process meta) still attempts POST/queue."""
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "FR-228: discovered mailSender must strip BOM before JWT mint or GitHub Closes skips",
        "-Lesson",
        "a-search notify mailSender: strip UTF-8 BOM from outbound HTML before signing session JWT.",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest lesson-MRB PASS loop" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout

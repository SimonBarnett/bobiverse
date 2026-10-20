"""FR #4917: harvest must not file tips after FIX/MRB on lesson or docs/mrb pin PRs.

Decide from PR shape (lesson / pin) and job kind (MRB, FIX, re-DONE), not only
``\\bMRB\\b`` regex. Acceptance: FIX DONE on docs/mrb-* and MRB DONE on
harvest-lesson both file nothing.
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


def test_fr4917_script_documents_lesson_or_pin_job_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #4917" in text
    assert "Test-HarvestLessonOrPinJobSkip" in text or "Test-HarvestLessonReviewLoop" in text
    assert "HARVEST_SCRIPT_VERSION" in text or "HarvestScriptVersion" in text
    assert "SKIPPED harvest lesson/pin job" in text or "lesson-or-pin" in text.lower()


def test_fr4917_fix_done_on_docs_mrb_pin_does_not_queue(tmp_path: Path):
    """FIX DONE on a docs/mrb pin PR must not open another harvest tip."""
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "FIX a-search#4683: docs/mrb-4680 CONFLICTING on mrb4661 pin; "
        "one main fold keep-both fuller must-skip; pins green; pushed 6a1e272",
        "-Lesson",
        "a-search FIX when docs/mrb tip CONFLICTING only on mrb4661 pin comment: "
        "keep fuller must-skip asserts; DONE FIX; no CI poll",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_fr4917_mrb_done_on_harvest_lesson_still_skips(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "MRB a-search#4700 PASS light-triage harvest-lesson tip CLOSED-duplicate; done",
        "-Lesson",
        "a-search harvest-lesson MRB: CLOSED-duplicate tip is FAIL-supersede; DONE PASS",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest" in r.stdout
    assert "HARVESTED" not in r.stdout


def test_fr4917_intake_detects_fix_on_docs_mrb():
    import intake

    assert intake.is_lesson_review_meta_loop(
        "FIX a-search#4683: docs/mrb-4680 CONFLICTING on mrb4661 pin; DONE FIX\n"
        "keep fuller must-skip asserts; DONE FIX; no CI poll"
    )


def test_fr4917_gitclaim_docs_mrb_and_lesson_chain():
    import gitclaim

    assert gitclaim.is_docs_mrb_pin_pr(
        title="docs/mrb-4680: pin fr4427 lesson", head_ref="docs/mrb-4680"
    )
    assert gitclaim.is_lesson_or_pin_pr(
        title="lesson(harvest-agent-skills): tip",
        labels=("harvest-lesson",),
        head_ref="intake/in_abc",
    )
    assert gitclaim.is_lesson_of_lesson_pr(
        title="lesson(harvest-agent-skills): Harvest tip restating mrb4661",
        body="CLOSED-duplicate; DONE PASS\nRefs SimonBarnett/a-search#4683",
        labels=("harvest-lesson",),
        head_ref="intake/in_x",
    )
    assert not gitclaim.is_lesson_of_lesson_pr(
        title="lesson(harvest-agent-skills): fill-madeira must skip disabled registry sources",
        body="Product playbook for soft-deploy.\n_via-intake_",
        labels=("harvest-lesson",),
        head_ref="intake/in_y",
    )

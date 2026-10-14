"""FR #3959 / #3957: FAIL-supersede skip must catch durable-home / do-not-park cues.

Incident: after MRB FAIL-supersede of #3955/#3956, Invoke-BobiverseHarvest filed
lesson text:

  FAIL-supersede: do not park FR #3948 MRB merge-on-green under harvest/SKILL.md;
  durable home is bobiverse-bob-job-mrb CAST IRON via #3950/#3952 (FR #2970)

Existing cues only matched ``durable in bobiverse-bob-job-mrb`` and contiguous
``park under harvest``, so intake opened twin tip #3958.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
MRB_SKILL = "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST_PS1.is_file():
    HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

# Exact class from bobiverse#3959 / tip #3958
INCIDENT_LESSON = (
    "FAIL-supersede: do not park FR #3948 MRB merge-on-green under harvest/SKILL.md; "
    "durable home is bobiverse-bob-job-mrb CAST IRON via #3950/#3952 (FR #2970)"
)
INCIDENT_SUMMARY = (
    "MRB bobiverse#3956 FAIL-superseded twin of #3955; FR #3948 CAST IRON already "
    "on main via #3950/#3952 in bobiverse-bob-job-mrb; tip closed unmerged"
)

HARVEST_COVERED = """# Harvest

## Harvested lessons (intake)

- Harvest-lesson MRB playbooks belong in `bobiverse-bob-job-mrb`. If intake files them under `harvest`, MRB moves/folds them there - do not land a second copy in this book (MRB #2740 / #2749).
"""

MRB_COVERED = """# bobiverse bob - MRB job

## FR #3948 - hand off after push; never poll CI (durable)

CAST IRON merge-on-green. FAIL-supersede wrong-book tips that park this under harvest.
"""


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


def test_fr3959_detects_durable_home_and_do_not_park_cues():
    blob = INCIDENT_SUMMARY + "\n" + INCIDENT_LESSON
    assert intake.is_mrb_process_routing_lesson(blob)
    assert intake.is_mrb_process_routing_lesson(INCIDENT_LESSON)
    # Synonyms covered
    assert intake.is_mrb_process_routing_lesson(
        "FAIL-supersede; durable home is bobiverse-bob-job-mrb"
    )
    assert intake.is_mrb_process_routing_lesson(
        "do not park this under harvest/SKILL.md; FAIL-supersede"
    )
    # Thin path: CAST IRON already on main (order flipped vs already CAST IRON)
    assert intake.is_fail_supersede_thin_twin_lesson(INCIDENT_SUMMARY)
    # Bare FAIL-supersede + product tip still must not match process routing alone
    assert not intake.is_mrb_process_routing_lesson(
        "Earlier MRB FAIL-superseded a twin; MSI RunInstall SkipCopy"
    )


def test_fr3959_intake_skips_incident_lesson(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = HARVEST_COVERED
    filer.repo_files[MRB_SKILL] = MRB_COVERED
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #3956 FAIL-superseded twin",
            "body": (
                f"Session summary:\n{INCIDENT_SUMMARY}\n\n"
                f"Lessons:\n- {INCIDENT_LESSON}\n"
            ),
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
                "seat": "flamingo-11336",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_3959_skip")
    assert rec["state"] == "lesson_already_covered"
    assert filer.prs == []
    assert filer.issues == []


def test_fr3959_ps1_client_skips_incident_lesson():
    if not HARVEST_PS1.is_file():
        return
    proc = _run_harvest(
        "-Repo",
        REPO,
        "-Summary",
        INCIDENT_SUMMARY,
        "-Lesson",
        INCIDENT_LESSON,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert "SKIPPED harvest FAIL-supersede" in out or "SKIPPED" in out
    assert "HARVESTED" not in out

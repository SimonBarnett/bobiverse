"""FR #3957: FAIL-supersede skip must catch 'durable home is job-mrb' and 'park X under harvest'.

Incident chain #3951/#3953/#3955/#3956/#3958: after FAIL-superseding a wrong-book tip,
Invoke-BobiverseHarvest with Lesson:
  'FAIL-supersede: do not park FR #3948 ... under harvest/SKILL.md; durable home is
   bobiverse-bob-job-mrb CAST IRON via #3950/#3952 (FR #2970).'
still POSTed a new lesson(harvest) tip. FR #3827 only matched 'durable in' and
'parked under harvest' (no words between park and under).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
MRB_SKILL = "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

# Exact class from issue #3957 / tip #3956
INCIDENT_LESSON = (
    "FAIL-supersede: do not park FR #3948 MRB merge-on-green under harvest/SKILL.md; "
    "durable home is bobiverse-bob-job-mrb CAST IRON via #3950/#3952 (FR #2970)."
)
INCIDENT_SUMMARY = (
    "MRB #3955 FAIL-supersede: harvest tip restated FR #3948 under harvest/SKILL.md; "
    "durable CAST IRON already on main in bobiverse-bob-job-mrb via #3950; closed unmerged"
)

HARVEST_COVERED = """# Harvest

## Harvested lessons (intake)

- Harvest-lesson MRB playbooks belong in `bobiverse-bob-job-mrb`. If intake files them under `harvest`, MRB moves/folds them there - do not land a second copy in this book (MRB #2740 / #2749).
"""

MRB_COVERED = """# bobiverse bob - MRB job

## FR #3948 - hand off after push; never poll CI (durable)
**CAST IRON already covers it:** FAIL-supersede harvest restatement tips when product is on main.
**Behind-main:** merge origin/main into the tip before merge.
## Harvest-lesson intake PRs (FR #2705)
Twin harvest-lesson PRs: FAIL-superseded the later one. Open docs/mrb-N after skill merge.
"""


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("BOB_OUTBOX", "BOB_JOB_REPO")}
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
        env=env,
    )


def test_fr3957_intake_detects_durable_home_is_and_park_x_under_harvest():
    blob = INCIDENT_SUMMARY + "\n" + INCIDENT_LESSON
    assert intake.is_mrb_process_routing_lesson(blob)
    # Synonyms that must match after this FR
    assert intake.is_mrb_process_routing_lesson(
        "FAIL-supersede; durable home is bobiverse-bob-job-mrb; FR #2970"
    )
    assert intake.is_mrb_process_routing_lesson(
        "FAIL-supersede: do not park FR #3948 under harvest/SKILL.md"
    )
    # MRB #2973: bare FAIL-supersede without job-mrb / park cues still False
    assert not intake.is_mrb_process_routing_lesson(
        "MRB #2967 FAIL-superseded: closed unmerged; filed covering PR"
    )


def test_fr3957_intake_skips_incident_when_job_mrb_covered(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = HARVEST_COVERED
    filer.repo_files[MRB_SKILL] = MRB_COVERED
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #3955 FAIL-supersede",
            "body": (
                f"Session summary:\n{INCIDENT_SUMMARY}\n\n"
                f"Lessons:\n- {INCIDENT_LESSON}\n"
            ),
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
            "idempotency_key": "hv-fr3957-incident",
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr3957")
    assert rec["state"] == "lesson_already_covered"
    assert filer.prs == []


def test_fr3957_harvest_script_skips_incident_wording(tmp_path: Path):
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "FR #3957" in text
    assert "durable home is" in text.lower() or "durable\\s+home\\s+is" in text.lower()

    outbox = tmp_path / "harvest-outbox"
    r = _run_harvest(
        "-Repo",
        REPO,
        "-Summary",
        INCIDENT_SUMMARY,
        "-Lesson",
        INCIDENT_LESSON,
        "-OutboxDir",
        str(outbox),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr3957_real_product_lesson_still_posts(tmp_path: Path):
    outbox = tmp_path / "harvest-outbox"
    r = _run_harvest(
        "-Repo",
        REPO,
        "-Summary",
        "FR #3957: QuietExec quote playbook for Install-Airc SetInstallCmd",
        "-Lesson",
        "Install-Airc QuietExec: quote SetInstallCmd paths on WinPS 5.1 (FR #3741).",
        "-OutboxDir",
        str(outbox),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout

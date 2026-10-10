"""FR #3827: tighten FAIL-supersede skip for CAST IRON / stay-in-job-mrb restatements.

Incident: after FAIL-superseding tip #3825, harvest opened #3826 with:
  'FAIL-supersede / thin harvest restatement playbooks stay in bobiverse-bob-job-mrb;
   do not append a second copy under harvest/SKILL.md'
FR #2970/#2991 cues required 'belong(s) in' / 'thin harvest lesson(s)' and missed
'stay in' / 'thin harvest tip' / 'second copy under harvest'.
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

# Exact class from issue #3827 / tip #3826
INCIDENT_LESSON = (
    "FAIL-supersede / thin harvest restatement playbooks stay in "
    "bobiverse-bob-job-mrb; do not append a second copy under harvest/SKILL.md "
    "(FR #2970/#2991)"
)
INCIDENT_SUMMARY = (
    "MRB bobiverse#3825 FAIL-superseded thin harvest tip restating FAIL-supersede "
    "process; durable in bobiverse-bob-job-mrb CAST IRON"
)

HARVEST_COVERED = """# Harvest

## Harvested lessons (intake)

- Harvest-lesson MRB playbooks belong in `bobiverse-bob-job-mrb`. If intake files them under `harvest`, MRB moves/folds them there - do not land a second copy in this book (MRB #2740 / #2749).
"""

MRB_COVERED = """# bobiverse bob - MRB job

**CAST IRON already covers it:** FAIL-supersede harvest restatement tips when product is on main.
**Behind-main:** merge origin/main into the tip before merge.
## Harvest-lesson intake PRs (FR #2705)
Twin harvest-lesson PRs: FAIL-superseded the later one.
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


def test_fr3827_detects_stay_in_job_mrb_and_thin_tip_cues():
    blob = INCIDENT_SUMMARY + "\n" + INCIDENT_LESSON
    assert intake.is_mrb_process_routing_lesson(blob)
    assert intake.is_fail_supersede_thin_twin_lesson(blob)
    # Synonyms that also must match
    assert intake.is_mrb_process_routing_lesson(
        "FAIL-supersede; durable in bobiverse-bob-job-mrb; second copy under harvest"
    )
    assert intake.is_fail_supersede_thin_twin_lesson(
        "FAIL-superseded thin harvest tip; already CAST IRON in job-mrb"
    )
    # MRB #2973: bare FAIL-supersede without process/thin cues still False
    assert not intake.is_mrb_process_routing_lesson(
        "MRB #2967 FAIL-superseded: closed unmerged; filed covering PR"
    )
    assert not intake.is_fail_supersede_thin_twin_lesson(
        "MRB #2967 FAIL-superseded: closed unmerged; filed covering PR"
    )


def test_fr3827_intake_skips_incident_lesson_when_covered(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = HARVEST_COVERED
    filer.repo_files[MRB_SKILL] = MRB_COVERED
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #3825 FAIL-superseded",
            "body": (
                f"Session summary:\n{INCIDENT_SUMMARY}\n\n"
                f"Lessons:\n- {INCIDENT_LESSON}\n"
            ),
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
            "idempotency_key": "hv-fr3827-incident",
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr3827")
    assert rec["state"] == "lesson_already_covered"
    assert filer.prs == []


def test_fr3827_harvest_script_skips_incident_wording(tmp_path: Path):
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "FR #3827" in text
    assert "stay in" in text.lower() or "durable in" in text.lower()
    assert "thin harvest tip" in text.lower() or "thin\\s+harvest\\s+tip" in text.lower()

    # FR #3859: OutboxDir must be pytest tmp_path (no host D: drive required).
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
    assert "SKIPPED harvest FAIL-supersede process loop (FR #2970/#2991" in r.stdout or (
        "SKIPPED harvest FAIL-supersede" in r.stdout and "3827" in r.stdout
    )
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr3827_real_product_lesson_still_posts(tmp_path: Path):
    # FR #3859: OutboxDir must be pytest tmp_path (no host D: drive required).
    outbox = tmp_path / "harvest-outbox"
    r = _run_harvest(
        "-Repo",
        REPO,
        "-Summary",
        "FR #3827: QuietExec quote playbook for Install-Airc SetInstallCmd",
        "-Lesson",
        "Install-Airc QuietExec: quote SetInstallCmd paths on WinPS 5.1 (FR #3741).",
        "-OutboxDir",
        str(outbox),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout


def test_fr3859_outbox_dir_uses_tmp_path_not_host_d_drive():
    """Pin: -OutboxDir must use pytest tmp_path (hosts without a fixed drive letter)."""
    src = Path(__file__).read_text(encoding="utf-8")
    # Assemble needles so this pin source does not contain the forbidden literals.
    drive = "D:"
    slash = "/"
    bslash = "\\"
    old_job = "job-fr-bobiverse-" + "3827"
    forbidden = (
        f'Path("{drive}{slash}',
        f"Path('{drive}{slash}",
        f'Path(r"{drive}{bslash}',
        old_job,
    )
    for needle in forbidden:
        assert needle not in src, f"hardcoded OutboxDir residue: {needle!r}"
    assert "tmp_path: Path" in src
    assert 'tmp_path / "harvest-outbox"' in src
    # Both harvest-script tests take tmp_path
    assert src.count("tmp_path: Path") >= 2
    assert src.count('tmp_path / "harvest-outbox"') >= 2

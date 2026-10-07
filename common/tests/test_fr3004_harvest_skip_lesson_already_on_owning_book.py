"""FR #3004: do not open lesson(harvest) when the owning product skill already has the lesson.

After FR #2996 landed in bobiverse-bob-worker, default -Book harvest still opened
lesson(harvest) tips #3001-#3003 for the same bob-worker playbook.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
WORKER_SKILL = "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"

LESSON = (
    "bob-worker: done-miss release must set `_release_gen = _turn_gen` or a prior "
    "normal turn-end leaves nak/idle gated forever and `_run` spins on `wait(0)` (FR #2996)."
)

WORKER_COVERED = f"""# bobiverse bob - worker

## Harvested reliability rules

- {LESSON}
"""

HARVEST_BARE = """# Harvest

## Harvested lessons (intake)

- Unrelated harvest tip only.
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


def test_fr3004_resolve_harvest_default_yields_to_bob_worker_keywords():
    book, path = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: MRB #2997 PASS done-miss",
        body=f"Session summary:\nx\n\nLessons:\n- {LESSON}\n",
    )
    assert book == "bobiverse-bob-worker"
    assert path == WORKER_SKILL
    # Explicit non-harvest book still wins.
    book2, _ = intake.resolve_skill_book(
        skill_book="bobiverse-bob-job-mrb",
        title="harvest: x",
        body=f"Lessons:\n- {LESSON}\n",
    )
    assert book2 == "bobiverse-bob-job-mrb"
    # Plain harvest without product cues stays harvest.
    book3, path3 = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: session",
        body="Lessons:\n- generic tip with no product cue\n",
    )
    assert book3 == "harvest"
    assert path3 == HARVEST_SKILL


def test_fr3004_intake_skips_when_owning_book_already_has_lesson(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = HARVEST_BARE
    filer.repo_files[WORKER_SKILL] = WORKER_COVERED
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #2997 PASS done-miss release_gen",
            "body": (
                "Session summary:\nMRB #2997 PASS: done-miss release_gen sync\n\n"
                f"Lessons:\n- {LESSON}\n"
            ),
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
                "seat": "marchhare-12536",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_3004_skip")
    assert rec["state"] == "lesson_already_covered"
    assert rec.get("skill_book") == "bobiverse-bob-worker"
    assert filer.prs == []


def test_fr3004_intake_routes_new_bob_worker_lesson_to_owning_book(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = HARVEST_BARE
    filer.repo_files[WORKER_SKILL] = "# bob-worker\n\nIntro only.\n"
    tip = "bob-worker: after done-miss, rebuild bob-worker.exe before expecting !bored (FR #2996)."
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: FR #2996 live rebuild note",
            "body": f"Session summary:\nx\n\nLessons:\n- {tip}\n",
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_3004_route")
    assert rec["state"] == "filed"
    assert rec.get("skill_book") == "bobiverse-bob-worker"
    assert filer.prs
    paths = [f.get("path") for f in (filer.prs[-1].get("files") or [])]
    assert WORKER_SKILL in paths
    assert HARVEST_SKILL not in paths
    assert tip in (filer.prs[-1].get("files") or [{}])[0].get("content", "")


def test_fr3004_harvest_script_infers_bob_worker_book():
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "FR #3004" in text
    assert "bobiverse-bob-worker" in text
    # Default harvest + bob-worker lesson should set skill_book in payload path.
    assert "Infer" in text or "infer" in text or "_release_gen" in text

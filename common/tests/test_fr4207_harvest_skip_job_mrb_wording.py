"""FR #4207: FAIL-supersede process-loop skip must match 'already in job-mrb' / FR #2970 / process loops."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    env = dict(**{k: v for k, v in __import__("os").environ.items() if k != "BOB_OUTBOX"})
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            "-Repo",
            "SimonBarnett/bobiverse",
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


def test_fr4207_script_documents_broadened_cues():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #4207" in text
    assert "Test-HarvestFailSupersedeProcessLoop" in text
    assert "already in" in text
    assert "process[- ]loops?" in text or "process loops" in text.lower()


def test_fr4207_skips_already_in_job_mrb_without_process_loops(tmp_path: Path):
    """Gap on tip: FAIL-supersede + already in job-mrb (no process-loop / belong-in cues) must still skip."""
    r = _run_harvest(
        "-Summary",
        "MRB FAIL-superseded: SeatDisk harvest tip already in job-mrb; closed unmerged",
        "-Lesson",
        "FAIL-supersede citing merged skill-book PR, close twin, DONE FAIL",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout


def test_fr4207_skips_fr2970_token_with_fail_supersede(tmp_path: Path):
    """FR #2970 alone with FAIL-supersede (no process-loop / job-mrb phrasing) must skip."""
    r = _run_harvest(
        "-Summary",
        "FAIL-superseded harvest tip; FR #2970",
        "-Lesson",
        "FAIL-supersede and close as not planned",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" in r.stdout


def test_fr4207_still_posts_unrelated_new_playbook(tmp_path: Path):
    r = _run_harvest(
        "-Summary",
        "FR #4207: broadened harvest skip cues for job-mrb wording",
        "-Lesson",
        "Clear-BobiverseSeatDisk -Reclaim runs before capacity intake when JobWorktrees leaves FreeGB low.",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    # Real product playbook: no FAIL-supersede token → must post/queue.
    assert "SKIPPED harvest FAIL-supersede process loop" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
